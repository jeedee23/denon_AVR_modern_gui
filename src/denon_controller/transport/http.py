from __future__ import annotations

import http.client
import ipaddress
import re
import socket
from urllib.parse import quote

from denon_controller.settings import Settings

STATUS_PATHS = (
    "/goform/formMainZone_MainZoneXmlStatus.xml",
    "/goform/formMainZone_MainZoneXml.xml",
)
ZONE2_PATH = "/goform/formZone2_Zone2XmlStatus.xml"
DEVICE_PATH = "/goform/Deviceinfo.xml"
PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(net)
    for net in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "169.254.0.0/16",
        "fc00::/7",
        "fe80::/10",
    )
)


def private_address(host: str) -> str:
    """Resolve once and pin connections; reject mixed public/private DNS answers."""
    answers = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    addresses = [answer[4][0] for answer in answers]
    if not addresses:
        raise ValueError("Receiver hostname has no address.")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not any(ip.version == net.version and ip in net for net in PRIVATE_NETWORKS):
            raise ValueError("Only a configured private LAN receiver is allowed.")
    return addresses[0]


def validate_command(command: str) -> None:
    fixed = {"PWON", "PWSTANDBY", "MUON", "MUOFF", "MVUP", "MVDOWN"}
    if command in fixed or re.fullmatch(r"MV\d{2}5?", command):
        return
    if re.fullmatch(r"SI[A-Z0-9 /-]{1,20}", command):
        return
    raise ValueError("Command is not allowlisted.")


class HttpTransport:
    def __init__(self, settings: Settings, address: str | None = None) -> None:
        self.settings = settings
        self.address = address or private_address(settings.host)

    def get(self, path: str) -> bytes:
        allowed = (*STATUS_PATHS, ZONE2_PATH, DEVICE_PATH)
        if path not in allowed and not path.startswith("/goform/formiPhoneAppDirect.xml?"):
            raise ValueError("Endpoint is not allowlisted.")
        if "?" in path:
            from urllib.parse import unquote

            validate_command(unquote(path.split("?", 1)[1]))
        connection = http.client.HTTPConnection(
            self.address, self.settings.http_port, timeout=self.settings.timeout
        )
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            if response.status != 200:
                raise OSError(f"HTTP status {response.status}")
            data = response.read(65537)
            if len(data) > 65536:
                raise ValueError("Oversized HTTP response.")
            return data
        finally:
            connection.close()

    def send(self, command: str) -> None:
        validate_command(command)
        self.get("/goform/formiPhoneAppDirect.xml?" + quote(command, safe=""))

    def close(self) -> None:
        pass
