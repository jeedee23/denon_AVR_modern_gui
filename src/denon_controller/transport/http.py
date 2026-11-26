from __future__ import annotations

import http.client
import ipaddress
import queue
import re
import socket
import threading
import time
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


def private_address(
    host: str,
    *,
    timeout: float = 1.5,
    cancelled: threading.Event | None = None,
) -> str:
    """Resolve once and pin connections; reject mixed public/private DNS answers."""
    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        result: queue.Queue[list | Exception] = queue.Queue(maxsize=1)

        def resolve() -> None:
            try:
                result.put(socket.getaddrinfo(host, None, type=socket.SOCK_STREAM))
            except Exception as exc:
                result.put(exc)

        threading.Thread(target=resolve, daemon=True).start()
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or cancelled is not None and cancelled.is_set():
                raise TimeoutError("Receiver name lookup timed out or was cancelled.") from None
            try:
                answers = result.get(timeout=min(0.05, remaining))
                break
            except queue.Empty:
                pass
        if isinstance(answers, Exception):
            raise answers from None
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
    def __init__(
        self,
        settings: Settings,
        address: str | None = None,
        *,
        cancelled: threading.Event | None = None,
    ) -> None:
        self.settings = settings
        self.cancelled = cancelled or threading.Event()
        self.address = address or private_address(
            settings.host,
            timeout=settings.timeout,
            cancelled=self.cancelled,
        )

    def get(self, path: str) -> bytes:
        if self.cancelled.is_set():
            raise OSError("HTTP request cancelled.")
        allowed = (*STATUS_PATHS, ZONE2_PATH, DEVICE_PATH)
        if path not in allowed and not path.startswith("/goform/formiPhoneAppDirect.xml?"):
            raise ValueError("Endpoint is not allowlisted.")
        if "?" in path:
            from urllib.parse import unquote

            validate_command(unquote(path.split("?", 1)[1]))
        connection = http.client.HTTPConnection(
            self.address, self.settings.http_port, timeout=self.settings.timeout
        )
        deadline = time.monotonic() + self.settings.timeout
        done = threading.Event()
        aborted = threading.Event()
        watchdog: threading.Thread | None = None
        try:
            connection.connect()
            network_socket = connection.sock

            def enforce_deadline() -> None:
                while not done.is_set():
                    remaining = deadline - time.monotonic()
                    if self.cancelled.is_set() or remaining <= 0:
                        aborted.set()
                        try:
                            network_socket.shutdown(socket.SHUT_RDWR)
                        except OSError:
                            pass
                        return
                    done.wait(min(0.05, remaining))

            watchdog = threading.Thread(target=enforce_deadline, daemon=True)
            watchdog.start()
            connection.request("GET", path)
            response = connection.getresponse()
            if response.status != 200:
                raise OSError(f"HTTP status {response.status}")
            data = response.read(65537)
            if aborted.is_set() or time.monotonic() >= deadline:
                raise TimeoutError("HTTP request deadline exceeded or cancelled.")
            if len(data) > 65536:
                raise ValueError("Oversized HTTP response.")
            return data
        except (OSError, http.client.HTTPException):
            if aborted.is_set() or self.cancelled.is_set():
                raise TimeoutError("HTTP request deadline exceeded or cancelled.") from None
            raise
        finally:
            done.set()
            if watchdog:
                watchdog.join()
            connection.close()

    def send(self, command: str) -> None:
        validate_command(command)
        self.get("/goform/formiPhoneAppDirect.xml?" + quote(command, safe=""))

    def close(self) -> None:
        self.cancelled.set()
