from unittest.mock import patch

import pytest

from denon_controller.transport.discovery import (
    SSDP_ADDRESS,
    DiscoveredReceiver,
    _description_device,
    _location_from_response,
    discover_receivers,
)

DENON_XML = b"""<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0"><device>
<friendlyName>Living Room AVR</friendlyName><manufacturer>Denon</manufacturer>
<modelName>AVR-X3400H</modelName></device></root>"""


def _response(location: str) -> bytes:
    return f"HTTP/1.1 200 OK\r\nLOCATION: {location}\r\n\r\n".encode()


def test_identifies_denon_description_without_inventing_model() -> None:
    assert _description_device(DENON_XML, "192.168.1.42") == DiscoveredReceiver(
        "192.168.1.42", "Living Room AVR", "AVR-X3400H"
    )
    assert (
        _description_device(
            b"<root><device><manufacturer>Other</manufacturer></device></root>", "192.168.1.43"
        )
        is None
    )


@pytest.mark.parametrize(
    "location",
    [
        "http://8.8.8.8/device.xml",
        "http://192.168.1.43/device.xml",
        "http://user:pass@192.168.1.42/device.xml",
        "https://192.168.1.42/device.xml",
        "http://localhost/device.xml",
        "http://192.168.1.42:bad/device.xml",
    ],
)
def test_rejects_untrusted_description_urls(location: str) -> None:
    assert _location_from_response(_response(location), "192.168.1.42") is None


def test_discovers_and_deduplicates_ssdp_responses() -> None:
    response = _response("http://192.168.1.42:60006/upnp/desc.xml")
    with (
        patch("denon_controller.transport.discovery.socket.socket") as socket_factory,
        patch("denon_controller.transport.discovery._fetch_description", return_value=DENON_XML),
    ):
        sock = socket_factory.return_value.__enter__.return_value
        sock.recvfrom.side_effect = [
            (response, ("192.168.1.42", 1900)),
            (response, ("192.168.1.42", 1900)),
            TimeoutError(),
        ]
        result = discover_receivers()
    assert result.receivers == (
        DiscoveredReceiver("192.168.1.42", "Living Room AVR", "AVR-X3400H"),
    )
    assert result.failed_descriptions == 0
    assert sock.sendto.call_args.args[1] == SSDP_ADDRESS
    assert b"M-SEARCH" in sock.sendto.call_args.args[0]


def test_failed_description_is_reported() -> None:
    response = _response("http://192.168.1.42/device.xml")
    with (
        patch("denon_controller.transport.discovery.socket.socket") as socket_factory,
        patch("denon_controller.transport.discovery._fetch_description", side_effect=OSError),
    ):
        sock = socket_factory.return_value.__enter__.return_value
        sock.recvfrom.side_effect = [(response, ("192.168.1.42", 1900)), TimeoutError()]
        result = discover_receivers()
    assert not result.receivers
    assert result.failed_descriptions == 1
