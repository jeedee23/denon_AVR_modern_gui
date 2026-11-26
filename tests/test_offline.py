from pathlib import Path
from unittest.mock import Mock

from denon_controller.models import Connection
from denon_controller.services.receiver import Receiver
from denon_controller.settings import Settings

FIXTURE = (Path(__file__).parent / "fixtures/main.xml").read_bytes()


def transports():
    receiver = Receiver(Settings())
    receiver.http = Mock()
    receiver.tcp = Mock()
    receiver.tcp.socket = None
    receiver.tcp.connect.side_effect = TimeoutError("offline")
    receiver.next_metadata = float("inf")
    return receiver


def test_http_fallback_when_tcp_unavailable():
    receiver = transports()
    receiver.http.get.return_value = FIXTURE
    state = receiver.poll()
    assert state.connection == Connection.CONNECTED
    assert state.protocol == "HTTP polling :8080"
    assert state.main.volume_db == -45.5
    receiver.http.send.assert_not_called()
    receiver.tcp.send.assert_not_called()


def test_unrecognized_200_does_not_mean_connected():
    receiver = transports()
    receiver.http.get.return_value = b"<html>not a receiver</html>"
    assert receiver.poll().connection == Connection.OFFLINE
    assert receiver.state.main.power is None


def test_offline_clears_stale_state_and_recovers():
    receiver = transports()
    receiver.http.get.return_value = FIXTURE
    receiver.poll()
    receiver.http.get.side_effect = TimeoutError("receiver unreachable")
    assert receiver.poll().connection == Connection.OFFLINE
    assert receiver.state.main.volume_db is None
    receiver.http.get.side_effect = None
    assert receiver.poll().connection == Connection.CONNECTED
    receiver.http.send.assert_not_called()


def test_simulated_command_confirmed_only_after_poll():
    receiver = Receiver(Settings(), simulate=True)
    receiver.poll()
    receiver.action("power_on")
    assert receiver.state.main.power is False
    assert receiver.state.outcome == "Sent, awaiting confirmation"
    receiver.poll()
    assert receiver.state.main.power is True
    assert receiver.state.outcome.startswith("Confirmed by state readback")
