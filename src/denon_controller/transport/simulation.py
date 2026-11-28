"""Deterministic, hardware-free receivers for UI development and testing."""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from denon_controller.models import DeviceState, PowerState, ZoneState
from denon_controller.transport.telnet import (
    EQ_BANDS,
    EQ_GROUPS,
    TRIM_CHANNELS,
    ReceiverSnapshot,
    apply_line,
    db_to_eq_level,
    db_to_level,
    level_to_db,
)


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


class SimulatedTelnetController:
    """Drop-in stand-in for TelnetController that never touches the network.

    Commands update an internal state and produce the same event lines the
    real receiver emits, routed through the shared parser.
    """

    def __init__(
        self,
        host: str = "simulated",
        port: int = 23,
        timeout: float = 5.0,
        on_line: Callable[[str], None] | None = None,
        on_state: Callable[[ReceiverSnapshot], None] | None = None,
        on_connection: Callable[[bool, str], None] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.on_line = on_line
        self.on_state = on_state
        self.on_connection = on_connection
        self.snapshot = ReceiverSnapshot()
        self._power = "PWSTANDBY"
        self._main_zone = "ZMOFF"
        self._zone2 = "Z2OFF"
        self._volume = "MV45"
        self._muted = "MUOFF"
        self._input = "SISAT/CBL"
        self._mode = "MSMCH STEREO"
        self._geq = "PSGEQ OFF"
        self._trims = {code: 0.0 for code in TRIM_CHANNELS}
        self._eq = {group: [0.0] * len(EQ_BANDS) for group in EQ_GROUPS}

    def connect(self) -> None:
        self.snapshot.connected = True
        if self.on_connection is not None:
            self.on_connection(True, "Connected (simulation)")
        self.request_full_status()

    def disconnect(self) -> None:
        self.snapshot.connected = False
        if self.on_connection is not None:
            self.on_connection(False, "Disconnected")

    def request_full_status(self) -> None:
        self._emit(self._power, self._main_zone, self._zone2, self._volume, "MVMAX 73")
        self._emit(self._muted, self._input, self._mode, self._geq, "SSINFAISFSV 48K")
        self._emit(*self._trim_lines(), "CVEND")
        self._emit(*self._eq_lines(), "SSAEQLRSEND")

    def current_snapshot(self) -> ReceiverSnapshot:
        return self.snapshot.copy()

    def send(self, command: str) -> None:
        if self.on_line is not None:
            self.on_line(f"> {command}")
        if command == "PWON":
            self._power, self._main_zone = "PWON", "ZMON"
            self._emit(self._power, self._main_zone)
        elif command == "PWSTANDBY":
            self._power, self._main_zone = "PWSTANDBY", "ZMOFF"
            self._emit(self._power, self._main_zone)
        elif command in ("Z2ON", "Z2OFF"):
            self._zone2 = command
            self._emit(self._zone2)
        elif command.startswith("MV") and command[2:].strip().isdigit():
            self._volume = command
            self._emit(self._volume)
        elif command in ("MUON", "MUOFF"):
            self._muted = command
            self._emit(self._muted)
        elif command.startswith("SI") and not command.endswith("?"):
            self._input = command
            self._emit(self._input)
        elif command.startswith("MS") and not command.endswith("?"):
            self._mode = command
            self._emit(self._mode)
        elif command in ("PSGEQ ON", "PSGEQ OFF"):
            self._geq = command
            self._emit(self._geq)
        elif command.startswith("CV") and " " in command:
            code, value = command[2:].split(" ", 1)
            if code in self._trims and value.strip().isdigit():
                self._trims[code] = level_to_db(value.strip())
                self._emit(f"CV{code} {value.strip()}")
        elif command.startswith("SSAEQLRS") and " " in command:
            group, values = command[8:].split(" ", 1)
            parts = values.strip().split(":")
            if group in self._eq and len(parts) == len(EQ_BANDS):
                self._eq[group] = [level_to_db(part) for part in parts]
                self._emit(f"SSAEQLRS{group} {values.strip()}")
        elif command.endswith("?"):
            self.request_full_status()

    def _trim_lines(self) -> list[str]:
        return [f"CV{code} {db_to_level(db)}" for code, db in self._trims.items()]

    def _eq_lines(self) -> list[str]:
        return [
            f"SSAEQLRS{group} " + ":".join(db_to_eq_level(db) for db in bands)
            for group, bands in self._eq.items()
        ]

    def _emit(self, *lines: str) -> None:
        for line in lines:
            if self.on_line is not None:
                self.on_line(f"< {line}")
            if apply_line(self.snapshot, line) and self.on_state is not None:
                self.on_state(self.snapshot.copy())
