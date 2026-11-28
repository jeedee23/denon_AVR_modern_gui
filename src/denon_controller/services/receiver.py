"""High-level receiver operations and state refresh behavior."""

from typing import Protocol

from denon_controller.models import DeviceState


class Receiver(Protocol):
    def get_main_zone_status(self) -> DeviceState: ...

    def power_on(self) -> None: ...


class ReceiverService:
    def __init__(self, receiver: Receiver) -> None:
        self.receiver = receiver

    def refresh(self) -> DeviceState:
        return self.receiver.get_main_zone_status()

    def power_on(self) -> None:
        self.receiver.power_on()
