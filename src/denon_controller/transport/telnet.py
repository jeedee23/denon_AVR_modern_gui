from __future__ import annotations

import select
import socket
import time

from denon_controller.settings import Settings
from denon_controller.transport.http import private_address, validate_command

READ_QUERIES = ("PW?", "ZM?", "MV?", "MU?", "SI?", "MS?", "Z2?")


class TelnetTransport:
    """Bounded CR-delimited Denon IP stream (not an interactive Telnet shell)."""

    def __init__(self, settings: Settings, address: str | None = None) -> None:
        self.settings = settings
        self.address = address or private_address(settings.host, timeout=settings.timeout)
        self.socket: socket.socket | None = None
        self.buffer = b""

    def connect(self) -> None:
        self.socket = socket.create_connection(
            (self.address, self.settings.telnet_port), timeout=self.settings.timeout
        )
        self.socket.settimeout(0.1)

    def send(self, command: str) -> None:
        if command not in READ_QUERIES:
            validate_command(command)
        if self.socket is None:
            raise OSError("TCP is disconnected.")
        self.socket.sendall((command + "\r").encode("ascii"))

    def read(self, duration: float = 0.35) -> list[str]:
        if self.socket is None:
            raise OSError("TCP is disconnected.")
        deadline = time.monotonic() + duration
        lines = []
        while time.monotonic() < deadline:
            if not select.select([self.socket], [], [], max(0, deadline - time.monotonic()))[0]:
                break
            try:
                chunk = self.socket.recv(4096)
            except TimeoutError:
                continue
            if not chunk:
                raise OSError("TCP peer closed the connection.")
            self.buffer += chunk
            if len(self.buffer) > 65536:
                raise ValueError("Oversized TCP response.")
            while b"\r" in self.buffer:
                raw, self.buffer = self.buffer.split(b"\r", 1)
                lines.append(raw.decode("ascii", errors="replace").strip())
            if len(lines) > 256:
                raise ValueError("Too many TCP events.")
        return lines

    def query(self) -> list[str]:
        for command in READ_QUERIES:
            self.send(command)
        return self.read()

    def close(self) -> None:
        if self.socket:
            self.socket.close()
        self.socket = None
        self.buffer = b""
