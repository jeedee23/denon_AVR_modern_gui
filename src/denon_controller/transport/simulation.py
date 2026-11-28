"""Deterministic, hardware-free receiver for UI development and testing."""

from dataclasses import replace
from datetime import datetime

from denon_controller.models import DeviceState, PowerState, ZoneState


class SimulatedReceiver:
    def __init__(self) -> None:
        self.state = DeviceState(
            main_zone=ZoneState(
                power=PowerState.STANDBY,
                input_source="Not available",
                volume_db=None,
                muted=None,
            ),
            connected=True,
            updated_at=datetime.now().astimezone(),
            status_detail="Simulation",
        )

    def get_main_zone_status(self) -> DeviceState:
        return replace(self.state, updated_at=datetime.now().astimezone())

    def power_on(self) -> None:
        self.state = replace(
            self.state,
            main_zone=replace(self.state.main_zone, power=PowerState.ON),
            updated_at=datetime.now().astimezone(),
            status_detail="Simulation: powered on",
        )
