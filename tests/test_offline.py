from denon_controller.models import PowerState
from denon_controller.services.receiver import ReceiverService
from denon_controller.transport.simulation import SimulatedReceiver


def test_simulation_supports_safe_offline_ui_and_power_on_flow() -> None:
    receiver = SimulatedReceiver()
    service = ReceiverService(receiver)

    assert service.refresh().main_zone.power is PowerState.STANDBY
    service.power_on()
    assert service.refresh().main_zone.power is PowerState.ON
