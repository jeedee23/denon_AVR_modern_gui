from __future__ import annotations

import socket
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from denon_controller.transport.http import private_address


@dataclass(frozen=True)
class DiscoveredDevice:
    host: str
    description: str


def discover(timeout: float = 2.0) -> list[DiscoveredDevice]:
    """One explicit, bounded link-local SSDP search; never fetch advertised URLs."""
    request = (
        'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\n'
        "MX: 1\r\nST: urn:schemas-upnp-org:device:MediaRenderer:1\r\n\r\n"
    )
    devices = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        sock.settimeout(0.2)
        sock.sendto(request.encode("ascii"), ("239.255.255.250", 1900))
        deadline = time.monotonic() + min(5, max(0.2, timeout))
        count = 0
        while time.monotonic() < deadline and count < 64:
            try:
                data, peer = sock.recvfrom(8192)
            except TimeoutError:
                continue
            count += 1
            headers = {}
            for line in data.decode("ascii", errors="replace").splitlines()[1:]:
                if ":" in line:
                    key, value = line.split(":", 1)
                    headers[key.lower().strip()] = value.strip()
            location = urlsplit(headers.get("location", ""))
            if location.scheme != "http" or location.hostname != peer[0]:
                continue
            try:
                private_address(peer[0])
            except (OSError, ValueError):
                continue
            # A discovery descriptor is not a control endpoint or identity certification.
            devices[peer[0]] = DiscoveredDevice(peer[0], "UPnP renderer (identity unverified)")
    return list(devices.values())
