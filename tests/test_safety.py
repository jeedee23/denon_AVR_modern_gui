import pytest

from denon_controller.transport.http import HttpReceiver, ReceiverError


def test_rejects_non_local_receiver_address() -> None:
    with pytest.raises(ReceiverError, match="private/local"):
        HttpReceiver("8.8.8.8")


def test_rejects_invalid_command_destinations() -> None:
    with pytest.raises(ReceiverError):
        HttpReceiver("http://receiver.example")


def test_validates_port_and_timeout() -> None:
    with pytest.raises(ValueError):
        HttpReceiver("192.168.1.2", port=70000)
    with pytest.raises(ValueError):
        HttpReceiver("192.168.1.2", timeout=0.1)
