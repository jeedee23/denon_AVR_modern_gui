import http.client
import socket
import threading
import time
from unittest.mock import Mock

import pytest

from denon_controller.settings import Settings
from denon_controller.transport.http import HttpTransport, private_address


@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("trickle_headers", [False, True])
def test_http_total_deadline_and_cancellation(monkeypatch, cancel, trickle_headers):
    local, peer = socket.socketpair()
    local.settimeout(0.2)
    connection = http.client.HTTPConnection("receiver.example", timeout=0.2)
    connection.connect = lambda: setattr(connection, "sock", local)
    monkeypatch.setattr("http.client.HTTPConnection", Mock(return_value=connection))
    cancelled = threading.Event()
    transport = HttpTransport(Settings(timeout=0.2), "192.0.2.1", cancelled=cancelled)
    header = b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n"

    def serve():
        try:
            peer.recv(4096)
            if not trickle_headers:
                peer.sendall(header)
            for byte in header if trickle_headers else b"x" * 100:
                peer.sendall(bytes([byte]))
                time.sleep(0.03)
        except OSError:
            pass
        finally:
            peer.close()

    server = threading.Thread(target=serve)
    server.start()
    timer = threading.Timer(0.05, cancelled.set) if cancel else None
    if timer:
        timer.start()
    started = time.monotonic()
    try:
        with pytest.raises((OSError, http.client.HTTPException)):
            transport.send("PWON")
        assert time.monotonic() - started < 0.6
    finally:
        local.close()
        server.join(1)
        if timer:
            timer.join()
    assert not server.is_alive()


def test_name_resolution_is_bounded(monkeypatch):
    finished = threading.Event()

    def slow_dns(*args, **kwargs):
        finished.wait(1)
        return []

    monkeypatch.setattr(socket, "getaddrinfo", slow_dns)
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError, match="lookup"):
            private_address("receiver.example", timeout=0.05)
        assert time.monotonic() - started < 0.5
    finally:
        finished.set()
