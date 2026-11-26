from __future__ import annotations

import http.client
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

from denon_controller.models import (
    Connection,
    DeviceState,
    apply_device_xml,
    apply_event,
    apply_status_xml,
    encode_volume,
)
from denon_controller.services.diagnostics import Diagnostics, sanitize
from denon_controller.settings import Settings
from denon_controller.transport import ReceiverTransport
from denon_controller.transport.http import (
    DEVICE_PATH,
    STATUS_PATHS,
    ZONE2_PATH,
    HttpTransport,
    private_address,
)
from denon_controller.transport.simulation import SimulationTransport
from denon_controller.transport.telnet import TelnetTransport

NETWORK_ERRORS = (OSError, ValueError, ET.ParseError, http.client.HTTPException)


@dataclass
class Pending:
    field: str
    value: Any
    deadline: float


class Receiver:
    """Single-worker service. Writes are never retried, including uncertain writes."""

    def __init__(
        self,
        settings: Settings,
        *,
        simulate: bool = False,
        cancelled: threading.Event | None = None,
    ) -> None:
        self.settings = settings
        self.state = DeviceState()
        self.diagnostics = Diagnostics(settings.host)
        self.http: HttpTransport | None = None
        self.tcp: TelnetTransport | None = None
        self.simulation = SimulationTransport() if simulate else None
        self.candidates_enabled = simulate
        self.pending: dict[str, Pending] = {}
        self.indeterminate_fields: set[str] = set()
        self.cancelled = cancelled or threading.Event()
        self.last_command = float("-inf")
        self.next_tcp_attempt = 0.0
        self.next_metadata = 0.0
        self.status_path: str | None = None
        self.zone2_supported = False

    def _initialize(self) -> None:
        if self.http is None:
            address = private_address(
                self.settings.host,
                timeout=self.settings.timeout,
                cancelled=self.cancelled,
            )
            self.http = HttpTransport(self.settings, address, cancelled=self.cancelled)
            self.tcp = TelnetTransport(self.settings, address)

    def poll(self) -> DeviceState:
        if self.cancelled.is_set():
            return self.state
        started = time.monotonic()
        previous = self.state
        self.state = DeviceState(
            name=previous.name,
            sources=dict(previous.sources),
            outcome=previous.outcome,
            connection=Connection.CONNECTING,
        )
        try:
            if self.simulation:
                self.simulation.populate(self.state)
                self.state.protocol = "Simulation"
            else:
                self._initialize()
                observed = False
                assert self.tcp is not None and self.http is not None
                if self.tcp.socket is None and started >= self.next_tcp_attempt:
                    self.next_tcp_attempt = started + 30
                    try:
                        self.tcp.connect()
                    except NETWORK_ERRORS as exc:
                        self.tcp.close()
                        self.diagnostics.record("TCP fallback", str(exc))
                if self.tcp.socket:
                    try:
                        for line in self.tcp.query():
                            observed = apply_event(self.state, line) or observed
                        if observed:
                            self.state.protocol = f"TCP :{self.settings.telnet_port}"
                    except NETWORK_ERRORS as exc:
                        self.tcp.close()
                        self.diagnostics.record("TCP fallback", str(exc))
                if not observed:
                    paths = (self.status_path,) if self.status_path else STATUS_PATHS
                    for path in paths:
                        try:
                            if apply_status_xml(self.state, self.http.get(path)):
                                self.status_path = path
                                observed = True
                                break
                        except NETWORK_ERRORS as exc:
                            self.diagnostics.record("HTTP probe", str(exc))
                    if not observed:
                        self.status_path = None
                        raise OSError("No recognized receiver state; status endpoints unverified.")
                    self.state.protocol = f"HTTP polling :{self.settings.http_port}"
                if started >= self.next_metadata:
                    self.next_metadata = started + 60
                    try:
                        apply_device_xml(self.state, self.http.get(DEVICE_PATH))
                    except NETWORK_ERRORS as exc:
                        self.diagnostics.record("Input discovery", str(exc))
                    try:
                        self.zone2_supported = apply_status_xml(
                            self.state, self.http.get(ZONE2_PATH), "zone2"
                        )
                    except NETWORK_ERRORS:
                        self.zone2_supported = False
                elif self.zone2_supported:
                    try:
                        apply_status_xml(self.state, self.http.get(ZONE2_PATH), "zone2")
                    except NETWORK_ERRORS:
                        pass
            self.state.connection = Connection.CONNECTED
            self.state.last_seen = time.monotonic()
            self.state.roundtrip_ms = (self.state.last_seen - started) * 1000
            self._confirm(can_confirm=True)
            if self.settings.diagnostics_verbose:
                self.diagnostics.record("Status", self.summary())
        except NETWORK_ERRORS as exc:
            self.state.connection = Connection.OFFLINE
            self.state.last_error = sanitize(str(exc), self.settings.host)
            self.diagnostics.record("Offline", self.state.last_error)
            self._confirm()
        return self.state

    def receive_events(self) -> bool:
        if not self.tcp or not self.tcp.socket:
            return False
        updated = False
        try:
            for line in self.tcp.read(0.001):
                updated = apply_event(self.state, line) or updated
            if updated:
                self.state.last_seen = time.monotonic()
        except NETWORK_ERRORS as exc:
            self.tcp.close()
            self.state.connection = Connection.OFFLINE
            self.state.last_seen = None
            self.state.last_error = sanitize(str(exc), self.settings.host)
            return True
        return updated

    def summary(self) -> str:
        return (
            f"{self.state.protocol}; system={self.state.system_power}; "
            f"main={self.state.main.power}; volume={self.state.main.volume_db}; "
            f"mute={self.state.main.mute}"
        )

    def _value(self, field: str) -> Any:
        target: Any = self.state
        for part in field.split("."):
            target = getattr(target, part)
        return target

    def _confirm(self, *, can_confirm: bool = False) -> None:
        if not self.pending:
            return
        confirmed = False
        for field, pending in list(self.pending.items()):
            if can_confirm and self._value(field) == pending.value:
                del self.pending[field]
                self.indeterminate_fields.discard(field)
                self.diagnostics.record("Readback", f"{field}: confirmed by fresh state readback")
                confirmed = True
            elif time.monotonic() >= pending.deadline:
                del self.pending[field]
                self.indeterminate_fields.add(field)
                self.diagnostics.record("Readback", f"{field}: Indeterminate; no write retry")
        if self.indeterminate_fields:
            fields = ", ".join(sorted(self.indeterminate_fields))
            self.state.outcome = (
                "Sent, awaiting confirmation. " if self.pending else ""
            ) + f"Indeterminate: {fields} not confirmed; no write retry. Refresh state."
        elif self.pending:
            self.state.outcome = "Sent, awaiting confirmation"
        elif confirmed:
            self.state.outcome = "Confirmed by state readback (not a hardware certification)"

    def _require_fresh(self, field: str) -> None:
        if not self.state.is_fresh(field, min(10, self.settings.poll_interval * 2)):
            raise ValueError(f"Fresh readback required for {field}.")

    def action(self, action: str, value: Any = None) -> None:
        if self.cancelled.is_set():
            raise ValueError("Receiver is disconnected.")
        now = time.monotonic()
        if now - self.last_command < 0.4:
            raise ValueError("Rate limited; wait before sending another command.")
        safety_reducing = (
            action == "mute"
            and value is True
            or action == "volume_down"
            or action == "volume"
            and isinstance(value, (int, float))
            and self.state.main.volume_db is not None
            and value < self.state.main.volume_db
        )
        if self.pending and not safety_reducing:
            self._confirm()
            if self.pending:
                raise ValueError("A command is awaiting confirmation; refresh first.")
        fresh = (
            self.state.connection == Connection.CONNECTED
            and self.state.last_seen is not None
            and now - self.state.last_seen <= min(10, self.settings.poll_interval * 2)
        )
        if action != "power_on" and (not fresh or not self.candidates_enabled):
            raise ValueError("Fresh readback and explicit unverified-control opt-in are required.")
        field, expected = "", None
        match action:
            case "power_on":
                command, field, expected = "PWON", "main.power", True
            case "standby":
                self._require_fresh("system_power")
                if self.state.system_power is None:
                    raise ValueError("System power readback is unavailable.")
                command, field, expected = "PWSTANDBY", "system_power", False
            case "mute":
                self._require_fresh("main.mute")
                if type(value) is not bool or self.state.main.mute is None:
                    raise ValueError("Mute readback is unavailable.")
                if not value and (
                    self.state.main.volume_db is None
                    or self.state.main.volume_db > self.settings.volume_ceiling
                ):
                    raise ValueError("Lower measured volume to the safe ceiling before unmuting.")
                if not value:
                    self._require_fresh("main.volume_db")
                command, field, expected = "MUON" if value else "MUOFF", "main.mute", value
            case "volume" | "volume_up" | "volume_down":
                self._require_fresh("main.volume_db")
                current = self.state.main.volume_db
                if current is None:
                    raise ValueError("Volume readback is unavailable.")
                pending_volume = self.pending.get("main.volume_db")
                baseline = min(current, pending_volume.value) if pending_volume else current
                db = (
                    value
                    if action == "volume"
                    else max(-80, baseline + (0.5 if action == "volume_up" else -0.5))
                )
                if pending_volume and db > baseline:
                    raise ValueError("Pending volume target is quieter; await fresh readback.")
                encoded = encode_volume(db)
                if db > self.settings.volume_ceiling and db > baseline:
                    raise ValueError("Volume exceeds the configured safe ceiling.")
                if db == current or pending_volume and db == pending_volume.value:
                    return
                # Absolute half-step writes avoid relative commands with ambiguous retries.
                command, field, expected = "MV" + encoded, "main.volume_db", db
            case "source":
                self._require_fresh("main.source")
                if value not in self.state.sources:
                    raise ValueError("Input must come from this receiver's reported input list.")
                command, field, expected = "SI" + value, "main.source", value
            case _:
                raise ValueError("Unsupported action.")
        if not self.simulation:
            self._initialize()
        transport: ReceiverTransport = self.simulation or self.http  # type: ignore[assignment]
        self.pending[field] = Pending(field, expected, now + 10)
        self.last_command = now
        self.state.outcome = "Sent, awaiting confirmation"
        if self.indeterminate_fields:
            self.state.outcome += "; previous indeterminate fields: " + ", ".join(
                sorted(self.indeterminate_fields)
            )
        self.diagnostics.record(action, "Sent, awaiting confirmation")
        try:
            transport.send(command)
        except NETWORK_ERRORS:
            self.state.outcome = "Indeterminate: send failed; refreshing, never retrying the write"
            self.diagnostics.record(action, self.state.outcome)

    def close(self) -> None:
        self.cancelled.set()
        for transport in (self.http, self.tcp, self.simulation):
            if transport:
                transport.close()
        self.state.connection = Connection.DISCONNECTED
        self.state.last_seen = None
        self.candidates_enabled = bool(self.simulation)
        self.pending.clear()
        self.indeterminate_fields.clear()
