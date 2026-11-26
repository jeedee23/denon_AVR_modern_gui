from pathlib import Path

import pytest

from denon_controller.models import (
    DeviceState,
    apply_device_xml,
    apply_event,
    apply_status_xml,
    parse_xml,
)


def test_http_zone_power_is_not_system_power():
    state = DeviceState()
    assert apply_status_xml(state, (Path(__file__).parent / "fixtures/main.xml").read_bytes())
    assert state.main.power is True
    assert state.system_power is None
    assert state.main.volume_db == -45.5
    assert state.main.mute is False
    assert state.surround == "STEREO"


def test_zones_are_distinct():
    state = DeviceState()
    for line in ("PWON", "ZMOFF", "Z2ON", "Z2455", "Z2MUON", "MV50", "MUOFF", "SIBD"):
        assert apply_event(state, line)
    assert state.system_power and not state.main.power
    assert state.zone2.power and state.zone2.mute
    assert state.zone2.volume_db == -34.5
    assert state.main.volume_db == -30
    assert state.main.source == "BD"


@pytest.mark.parametrize("line", ["MVUP", "MVMAX 70", "PW?", "MS?", "MV350", "garbage"])
def test_unknown_events_do_not_invent_state(line):
    state = DeviceState()
    assert not apply_event(state, line)
    assert state.main.volume_db is None


@pytest.mark.parametrize(
    "data",
    [
        b"<!DOCTYPE x [<!ENTITY x 'boom'>]><x>&x;</x>",
        b"x" * 65537,
    ],
)
def test_unsafe_xml(data):
    with pytest.raises(ValueError):
        parse_xml(data)


def test_source_list_is_reported_not_universal():
    state = DeviceState()
    apply_device_xml(
        state,
        b"""<Device><FriendlyName>Test AVR</FriendlyName>
    <InputSource><FuncName>BD</FuncName><Rename>My disc player</Rename></InputSource>
    <InputSource><FuncName>BD&#13;PWON</FuncName></InputSource></Device>""",
    )
    assert state.sources == {"BD": "My disc player"}
