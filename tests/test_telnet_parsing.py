"""Offline tests for the Telnet protocol parsing and value encodings.

All expectations mirror responses captured from the owner's AVR-X3400H on
2026-11-28 (docs/protocol.md).
"""

import pytest

from denon_controller.transport.telnet import (
    ReceiverSnapshot,
    apply_line,
    db_to_eq_level,
    db_to_level,
    format_volume_command,
    level_to_db,
    parse_volume,
)


def test_level_decoding_matches_receiver_samples() -> None:
    assert level_to_db("50") == 0.0
    assert level_to_db("57") == 7.0
    assert level_to_db("545") == 4.5
    assert level_to_db("38") == -12.0
    assert level_to_db("300") == -20.0
    assert level_to_db("560") == 6.0


def test_level_encoding_round_trips() -> None:
    assert db_to_level(0.0) == "50"
    assert db_to_level(7.0) == "57"
    assert db_to_level(4.5) == "545"
    assert db_to_level(-12.0) == "38"
    assert db_to_eq_level(0.0) == "500"
    assert db_to_eq_level(-20.0) == "300"
    assert db_to_eq_level(6.0) == "560"
    assert db_to_eq_level(-3.5) == "465"


def test_volume_parse_and_format() -> None:
    assert parse_volume("52") == 52.0
    assert parse_volume("525") == 52.5
    assert format_volume_command(50) == "MV50"
    assert format_volume_command(52.5) == "MV525"
    assert format_volume_command(5.0) == "MV05"
    with pytest.raises(ValueError):
        format_volume_command(99)


def test_apply_line_parses_receiver_event_stream() -> None:
    snapshot = ReceiverSnapshot()
    lines = [
        "PWON",
        "ZMON",
        "Z2ON",
        "MVMAX 73",
        "MV52",
        "MUOFF",
        "SISAT/CBL",
        "MSMCH STEREO",
        "SSINFAISFSV 48K",
        "PSGEQ ON",
        "PSMULTEQ:OFF",
        "PSBAS 50",
        "PSTRE 54",
        "CVFL 57",
        "CVSDL 545",
        "CVEND",
        "SSAEQLRSFRO 465:465:470:495:465:385:365:400:370",
        "SSAEQLRSEND",
    ]
    for line in lines:
        apply_line(snapshot, line)
    assert snapshot.power_on is True
    assert snapshot.main_zone_on is True
    assert snapshot.zone2_on is True
    assert snapshot.volume == 52.0
    assert snapshot.volume_max == 73.0
    assert snapshot.muted is False
    assert snapshot.input_source == "SAT/CBL"
    assert snapshot.sound_mode == "MCH STEREO"
    assert snapshot.sample_rate == "48K"
    assert snapshot.geq_on is True
    assert snapshot.multeq == "OFF"
    assert snapshot.tone_bass_db == 0.0
    assert snapshot.tone_treble_db == 4.0
    assert snapshot.trims_db["FL"] == 7.0
    assert snapshot.trims_db["SDL"] == 4.5
    assert snapshot.eq_bands_db["FRO"] == [-3.5, -3.5, -3.0, -0.5, -3.5, -11.5, -13.5, -10.0, -13.0]


def test_apply_line_ignores_noise_and_terminators() -> None:
    snapshot = ReceiverSnapshot()
    assert apply_line(snapshot, "CVEND") is False
    assert apply_line(snapshot, "SSAEQLRSEND") is False
    assert apply_line(snapshot, "SSSPCFRO LAR") is False
    assert apply_line(snapshot, "OPSTS 0000") is False
    assert snapshot.trims_db == {}
    assert snapshot.eq_bands_db == {}


def test_standby_and_zone_off_events() -> None:
    snapshot = ReceiverSnapshot()
    apply_line(snapshot, "PWSTANDBY")
    apply_line(snapshot, "ZMOFF")
    apply_line(snapshot, "Z2OFF")
    apply_line(snapshot, "MUON")
    assert snapshot.power_on is False
    assert snapshot.main_zone_on is False
    assert snapshot.zone2_on is False
    assert snapshot.muted is True
