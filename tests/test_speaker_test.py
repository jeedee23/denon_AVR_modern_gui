from denon_controller.transport.simulation import SimulatedTelnetController
from denon_controller.ui.speaker_test import SpeakerTestEngine


def test_session_switches_to_stream_direct_and_restores_mode() -> None:
    controller = SimulatedTelnetController()
    controller.connect()
    engine = SpeakerTestEngine(controller)

    engine._start_session()
    snapshot = controller.current_snapshot()
    assert engine.active
    assert snapshot.sound_mode == "DIRECT"
    assert snapshot.volume == 50.0
    assert engine.baseline_mode == "MCH STEREO"

    engine._end_session()
    snapshot = controller.current_snapshot()
    assert not engine.active
    assert snapshot.sound_mode == "MCH STEREO"
    assert snapshot.volume == 45.0
    assert engine.baseline_mode is None
