"""Typed state models used by transports, services, and the UI."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class PowerState(StrEnum):
    ON = "On"
    STANDBY = "Standby"
    UNKNOWN = "Unknown"


@dataclass(frozen=True, slots=True)
class ZoneState:
    power: PowerState = PowerState.UNKNOWN
    input_source: str | None = None
    volume_db: float | None = None
    muted: bool | None = None


@dataclass(frozen=True, slots=True)
class DeviceState:
    main_zone: ZoneState = ZoneState()
    surround_mode: str | None = None
    connected: bool = False
    updated_at: datetime | None = None
    status_detail: str = "Not connected"

    @property
    def is_stale(self) -> bool:
        if self.updated_at is None:
            return True
        return (datetime.now().astimezone() - self.updated_at).total_seconds() > 15
