"""Small HTTP client for the receiver's documented Denon endpoints."""

from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

from denon_controller.models import DeviceState, PowerState, ZoneState

POWER_ON_COMMAND = "PWON"
MAIN_ZONE_STATUS_PATH = "/goform/formMainZone_MainZoneXml.xml"
APP_DIRECT_PATH = "/goform/formiPhoneAppDirect.xml"


class ReceiverError(Exception):
    """A network, protocol, or receiver-response error."""


def _validate_private_destination(host: str) -> str:
    host = host.strip()
    if not host or any(char in host for char in "/?#@"):
        raise ReceiverError("Enter a receiver IP address or hostname")
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(result[4][0])
                for result in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
            }
        except socket.gaierror as exc:
            raise ReceiverError(f"Could not resolve receiver host: {exc}") from exc
    if not addresses or any(
        not (address.is_private or address.is_loopback or address.is_link_local)
        for address in addresses
    ):
        raise ReceiverError("Receiver address must resolve only to a private/local network")
    return host


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _xml_values(payload: bytes) -> dict[str, str]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ReceiverError(f"Receiver status was not valid XML: {exc}") from exc
    values: dict[str, str] = {}
    for element in root.iter():
        for child in element:
            if _local_name(child.tag) == "value" and child.text and child.text.strip():
                values[_local_name(element.tag)] = child.text.strip()
        if len(element) == 0 and element.text and element.text.strip():
            values[_local_name(element.tag)] = element.text.strip()
    return values


def parse_main_zone_status(payload: bytes) -> DeviceState:
    values = _xml_values(payload)
    power_text = values.get("power", "").upper()
    if power_text in {"ON", "1"}:
        power = PowerState.ON
    elif power_text in {"STANDBY", "OFF", "0"}:
        power = PowerState.STANDBY
    else:
        power = PowerState.UNKNOWN

    volume: float | None = None
    raw_volume = values.get("volume")
    if raw_volume:
        try:
            volume = float(raw_volume)
        except ValueError:
            volume = None

    mute_text = values.get("mute", "").upper()
    muted = True if mute_text in {"ON", "1"} else False if mute_text in {"OFF", "0"} else None
    return DeviceState(
        main_zone=ZoneState(
            power=power,
            input_source=values.get("inputfuncselect"),
            volume_db=volume,
            muted=muted,
        ),
        surround_mode=values.get("surroundmode"),
        connected=True,
        updated_at=datetime.now().astimezone(),
        status_detail="Status refreshed",
    )


class HttpReceiver:
    def __init__(self, host: str, port: int = 8080, timeout: float = 3.0) -> None:
        self.host = _validate_private_destination(host)
        if not 1 <= port <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        if not 0.2 <= timeout <= 15:
            raise ValueError("Timeout must be between 0.2 and 15 seconds")
        self.port = port
        self.timeout = timeout

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def _get(self, path: str, query: str = "") -> bytes:
        url = urllib.parse.urlunsplit(("http", f"{self.host}:{self.port}", path, query, ""))
        request = urllib.request.Request(url, headers={"User-Agent": "DenonAVRController/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.read(1_000_000)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ReceiverError(f"Receiver request failed: {exc}") from exc

    def get_main_zone_status(self) -> DeviceState:
        return parse_main_zone_status(self._get(MAIN_ZONE_STATUS_PATH))

    def power_on(self) -> None:
        # This is the one command confirmed by the owner on the X3400H.
        self._get(APP_DIRECT_PATH, urllib.parse.quote(POWER_ON_COMMAND, safe=""))
