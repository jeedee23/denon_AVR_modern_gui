from denon_controller.models import PowerState
from denon_controller.transport.http import parse_main_zone_status


def test_parses_main_zone_status_with_denon_style_xml() -> None:
    payload = b"""<item><Power><value>ON</value></Power>
    <InputFuncSelect><value>CBL/SAT</value></InputFuncSelect>
    <Volume><value>-35.0</value></Volume><Mute><value>OFF</value></Mute>
    <SurroundMode><value>Dolby Audio</value></SurroundMode></item>"""

    state = parse_main_zone_status(payload)

    assert state.connected
    assert state.main_zone.power is PowerState.ON
    assert state.main_zone.input_source == "CBL/SAT"
    assert state.main_zone.volume_db == -35.0
    assert state.main_zone.muted is False
    assert state.surround_mode == "Dolby Audio"


def test_unknown_values_remain_unknown() -> None:
    state = parse_main_zone_status(b"<item><Power><value>?</value></Power></item>")

    assert state.main_zone.power is PowerState.UNKNOWN
    assert state.main_zone.volume_db is None
