import socket
from unittest.mock import Mock

import pytest

from denon_controller.settings import Settings
from denon_controller.transport.http import HttpTransport
from denon_controller.transport.telnet import READ_QUERIES, TelnetTransport


def test_http_exact_owner_verified_command(monkeypatch):
    connection = Mock()
    connection.getresponse.return_value.status = 200
    connection.getresponse.return_value.read.return_value = b""
    factory = Mock(return_value=connection)
    monkeypatch.setattr("http.client.HTTPConnection", factory)
    transport = HttpTransport(Settings(), "192.0.2.1")
    transport.send("PWON")
    factory.assert_called_once_with("192.0.2.1", 8080, timeout=1.5)
    connection.request.assert_called_once_with("GET", "/goform/formiPhoneAppDirect.xml?PWON")
    connection.close.assert_called_once()


def test_http_no_redirect_or_oversized_body(monkeypatch):
    connection = Mock()
    response = connection.getresponse.return_value
    monkeypatch.setattr("http.client.HTTPConnection", Mock(return_value=connection))
    transport = HttpTransport(Settings(), "192.0.2.1")
    response.status = 302
    with pytest.raises(OSError):
        transport.send("PWON")
    response.status = 200
    response.read.return_value = b"x" * 65537
    with pytest.raises(ValueError):
        transport.send("PWON")


def test_tcp_queries_only_and_cr_termination():
    transport = TelnetTransport(Settings(), "192.0.2.1")
    transport.socket = Mock()
    transport.read = Mock(return_value=[])
    transport.query()
    assert [call.args[0] for call in transport.socket.sendall.call_args_list] == [
        (query + "\r").encode() for query in READ_QUERIES
    ]


def test_tcp_fragmented_unsolicited_events():
    local, peer = socket.socketpair()
    transport = TelnetTransport(Settings(), "192.0.2.1")
    transport.socket = local
    try:
        peer.sendall(b"PWON\rMV")
        assert transport.read(0.01) == ["PWON"]
        peer.sendall(b"455\rMUON\r")
        assert transport.read(0.01) == ["MV455", "MUON"]
    finally:
        transport.close()
        peer.close()


def test_tcp_closed_peer_is_offline():
    local, peer = socket.socketpair()
    transport = TelnetTransport(Settings(), "192.0.2.1")
    transport.socket = local
    peer.close()
    try:
        with pytest.raises(OSError, match="closed"):
            transport.read()
    finally:
        transport.close()
