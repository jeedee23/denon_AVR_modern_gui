import socket
import time
from unittest.mock import Mock

import pytest

from denon_controller.models import Connection
from denon_controller.services.receiver import Receiver
from denon_controller.settings import Settings
from denon_controller.transport.http import private_address, validate_command


def ready():
    receiver = Receiver(Settings(), simulate=True)
    receiver.poll()
    return receiver


def test_startup_is_read_only():
    receiver = ready()
    assert receiver.simulation.sent == []
    assert receiver.state.main.volume_db == -45


def test_volume_ceiling_allows_reduction_and_mute():
    receiver = ready()
    receiver.state.main.volume_db = -20
    with pytest.raises(ValueError, match="ceiling"):
        receiver.action("volume", -19)
    receiver.action("volume_down")
    assert receiver.simulation.sent == ["MV595"]
    receiver.last_command -= 1
    receiver.action("mute", True)
    assert receiver.simulation.sent[-1] == "MUON"


def test_duplicate_and_rate_limit():
    receiver = ready()
    receiver.action("volume", -45)
    assert receiver.simulation.sent == []
    receiver.action("volume_up")
    with pytest.raises(ValueError, match="Rate limited"):
        receiver.action("volume_up")
    assert len(receiver.simulation.sent) == 1


def test_stale_readback_cannot_increase_volume():
    receiver = ready()
    receiver.state.last_seen = time.monotonic() - 300
    with pytest.raises(ValueError, match="Fresh readback"):
        receiver.action("volume_up")
    assert not receiver.simulation.sent


def test_unverified_opt_in_required_even_with_readback():
    receiver = ready()
    receiver.candidates_enabled = False
    with pytest.raises(ValueError, match="opt-in"):
        receiver.action("mute", True)


def test_http_200_is_not_confirmation_and_no_retry():
    receiver = Receiver(Settings())
    receiver.http = Mock()
    receiver.action("power_on")
    assert receiver.state.main.power is None
    assert receiver.state.outcome == "Sent, awaiting confirmation"
    receiver.http.send.assert_called_once_with("PWON")
    receiver.http.send.side_effect = TimeoutError("timeout")
    receiver.pending.deadline -= 20
    receiver._confirm()
    assert "Indeterminate" in receiver.state.outcome
    receiver.http.send.assert_called_once()


def test_indeterminate_send_not_repeated():
    receiver = Receiver(Settings())
    receiver.http = Mock()
    receiver.http.send.side_effect = TimeoutError()
    receiver.action("power_on")
    assert "Indeterminate" in receiver.state.outcome
    receiver.last_command -= 1
    with pytest.raises(ValueError, match="awaiting"):
        receiver.action("power_on")
    receiver.http.send.assert_called_once()


def test_cached_pre_command_state_cannot_confirm_a_write():
    receiver = Receiver(Settings())
    receiver.http = Mock()
    receiver.state.main.power = True
    receiver.action("power_on")
    receiver.last_command -= 1
    with pytest.raises(ValueError, match="awaiting"):
        receiver.action("power_on")
    assert receiver.pending is not None
    assert receiver.state.outcome == "Sent, awaiting confirmation"
    receiver.http.send.assert_called_once()


def test_unmute_requires_measured_safe_volume():
    receiver = ready()
    receiver.state.main.volume_db = -20
    with pytest.raises(ValueError, match="before unmuting"):
        receiver.action("mute", False)
    receiver.action("mute", True)
    assert receiver.simulation.sent == ["MUON"]


@pytest.mark.parametrize("command", ["PWON\rMV98", "SIfoo?PWON", "PSMULTEQ:AUDYSSEY", "CVFL UP"])
def test_allowlist_rejects_raw_or_calibration_commands(command):
    with pytest.raises(ValueError):
        validate_command(command)


@pytest.mark.parametrize("address", ["8.8.8.8", "127.0.0.1", "::1", "100.64.0.1", "192.0.2.1"])
def test_non_lan_destinations_rejected(monkeypatch, address):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(0, 0, 0, "", (address, 0))])
    with pytest.raises(ValueError, match="private LAN"):
        private_address("receiver.example")


def test_dns_rebinding_mixed_answers_rejected(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(0, 0, 0, "", ("10.0.0.2", 0)), (0, 0, 0, "", ("203.0.113.1", 0))],
    )
    with pytest.raises(ValueError):
        private_address("receiver.example")


def test_offline_gate():
    receiver = ready()
    receiver.state.connection = Connection.OFFLINE
    with pytest.raises(ValueError):
        receiver.action("volume", -40)


def test_unknown_source_is_rejected():
    receiver = ready()
    with pytest.raises(ValueError, match="reported input"):
        receiver.action("source", "MADEUP")
