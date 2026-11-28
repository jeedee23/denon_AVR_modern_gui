"""Offline tests for sound profiles: round trip, command order, safety clamp."""

from denon_controller.profiles import (
    Profile,
    apply_commands,
    load_store,
    profile_from_dict,
    profile_from_snapshot,
    profile_to_dict,
    save_store,
)
from denon_controller.transport.telnet import ReceiverSnapshot, apply_line


def _snapshot() -> ReceiverSnapshot:
    snapshot = ReceiverSnapshot()
    for line in (
        "MV52",
        "MSMCH STEREO",
        "PSGEQ ON",
        "CVFL 57",
        "CVSDR 545",
        "SSAEQLRSFRO 465:465:470:495:465:385:365:400:370",
    ):
        apply_line(snapshot, line)
    return snapshot


def test_profile_round_trips_through_dict() -> None:
    profile = profile_from_snapshot("Movie night", _snapshot())
    restored = profile_from_dict("Movie night", profile_to_dict(profile))
    assert restored == profile
    assert restored.volume == 52.0
    assert restored.sound_mode == "MCH STEREO"
    assert restored.geq_on is True
    assert restored.trims_db == {"FL": 7.0, "SDR": 4.5}
    assert restored.eq_bands_db["FRO"][4] == -3.5


def test_apply_commands_clamps_volume_and_encodes_values() -> None:
    profile = profile_from_snapshot("Loud", _snapshot())
    commands = apply_commands(profile, volume_limit=50.0)
    assert commands[0] == "MV50"  # clamped from 52
    assert "MSMCH STEREO" in commands
    assert "PSGEQ ON" in commands
    assert "CVFL 57" in commands
    assert "CVSDR 545" in commands
    assert "SSAEQLRSFRO 465:465:470:495:465:385:365:400:370" in commands


def test_store_round_trip_and_missing_file(tmp_path) -> None:
    path = tmp_path / "profiles.json"
    assert load_store(path) == {"last": None, "auto_apply": True, "profiles": {}}
    store = {
        "last": "Evening",
        "auto_apply": False,
        "profiles": {"Evening": profile_to_dict(Profile(name="Evening", volume=40.0))},
    }
    save_store(store, path)
    loaded = load_store(path)
    assert loaded["last"] == "Evening"
    assert loaded["auto_apply"] is False
    assert profile_from_dict("Evening", loaded["profiles"]["Evening"]).volume == 40.0
