"""Discover Denon devices on the local network using SSDP and UPnP."""

from __future__ import annotations

import http.client
import ipaddress
import socket
import time
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.parser import BytesParser

from denon_controller.transport.http import ReceiverError

SSDP_ADDRESS = ("239.255.255.250", 1900)
SEARCH_REQUEST = (
    b"M-SEARCH * HTTP/1.1\r\n"
    b"HOST: 239.255.255.250:1900\r\n"
    b'MAN: "ssdp:discover"\r\n'
    b"MX: 2\r\n"
    b"ST: ssdp:all\r\n\r\n"
)


@dataclass(frozen=True, slots=True)
class DiscoveredReceiver:
    host: str
    name: str
    model: str


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    receivers: tuple[DiscoveredReceiver, ...]
    failed_descriptions: int = 0


def _location_from_response(data: bytes, sender: str) -> str | None:
    lines = data.split(b"\r\n", 1)
    if len(lines) != 2 or not lines[0].startswith(b"HTTP/1.1 200"):
        return None
    location = BytesParser().parsebytes(lines[1], headersonly=True).get("location")
    if not location:
        return None
    try:
        url = urllib.parse.urlsplit(location)
        sender_ip = ipaddress.ip_address(sender)
        location_ip = ipaddress.ip_address(url.hostname or "")
        port = url.port
    except ValueError:
        return None
    if (
        url.scheme.lower() != "http"
        or url.username is not None
        or url.password is not None
        or location_ip != sender_ip
        or not (sender_ip.is_private or sender_ip.is_link_local)
        or port == 0
    ):
        return None
    return location


def _description_device(payload: bytes, host: str) -> DiscoveredReceiver | None:
    root = ET.fromstring(payload)
    for device in root.iter():
        if device.tag.rsplit("}", 1)[-1].lower() != "device":
            continue
        fields = {
            child.tag.rsplit("}", 1)[-1].lower(): (child.text or "").strip() for child in device
        }
        name = fields.get("friendlyname", "")
        model = fields.get("modelname", "")
        manufacturer = fields.get("manufacturer", "")
        if "denon" in f"{manufacturer} {name} {model}".lower():
            return DiscoveredReceiver(host=host, name=name or model or "Denon", model=model)
    return None


def _fetch_description(location: str) -> bytes:
    url = urllib.parse.urlsplit(location)
    assert url.hostname is not None
    connection = http.client.HTTPConnection(url.hostname, url.port or 80, timeout=1.5)
    path = urllib.parse.urlunsplit(("", "", url.path or "/", url.query, ""))
    try:
        connection.request("GET", path, headers={"Accept": "text/xml, application/xml"})
        response = connection.getresponse()
        if response.status != 200:
            raise ReceiverError(f"Device description returned HTTP {response.status}")
        payload = response.read(262_145)
        if len(payload) > 262_144:
            raise ReceiverError("Device description exceeds size limit")
        return payload
    finally:
        connection.close()


def _local_ipv4_addresses() -> tuple[str, ...]:
    """Private IPv4 addresses of this machine; multicast must be sent per interface.

    On multi-homed hosts (e.g. VPN adapters) the OS default route may send the
    SSDP search out of the wrong interface, so we search each private one.
    """
    addresses: set[str] = set()
    try:
        host = socket.gethostname()
        for info in socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_DGRAM):
            candidate = info[4][0]
            try:
                ip = ipaddress.ip_address(candidate)
            except ValueError:
                continue
            if ip.is_private and not ip.is_loopback:
                addresses.add(candidate)
    except OSError:
        pass
    return tuple(sorted(addresses)) or ("0.0.0.0",)


def _search_on_interface(local_ip: str, timeout: float, locations: dict[str, str]) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        if local_ip != "0.0.0.0":
            sock.bind((local_ip, 0))
            sock.setsockopt(
                socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(local_ip)
            )
        sock.sendto(SEARCH_REQUEST, SSDP_ADDRESS)
        deadline = time.monotonic() + timeout
        while len(locations) < 32:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            sock.settimeout(remaining)
            try:
                data, address = sock.recvfrom(65535)
            except TimeoutError:
                break
            location = _location_from_response(data, address[0])
            if location:
                locations[location] = address[0]


def discover_receivers(timeout: float = 3.0) -> DiscoveryResult:
    """Send a bounded multicast search; no AVR control commands are sent."""
    locations: dict[str, str] = {}
    interfaces = _local_ipv4_addresses()
    failures: list[OSError] = []
    for local_ip in interfaces:
        try:
            _search_on_interface(local_ip, timeout, locations)
        except OSError as exc:
            failures.append(exc)
    if failures and len(failures) == len(interfaces):
        raise ReceiverError(f"Local discovery failed: {failures[-1]}") from failures[-1]

    receivers: dict[str, DiscoveredReceiver] = {}
    failures = 0
    for location, host in locations.items():
        try:
            receiver = _description_device(_fetch_description(location), host)
        except (OSError, http.client.HTTPException, ET.ParseError, ReceiverError):
            failures += 1
            continue
        if receiver:
            receivers.setdefault(receiver.host, receiver)
    return DiscoveryResult(tuple(sorted(receivers.values(), key=lambda item: item.name)), failures)
