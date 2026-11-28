"""Telnet (TCP port 23) transport with realtime event listening.

Every command and value encoding in this module was verified against the
owner's AVR-X3400H on 2026-11-28 (see docs/protocol.md). The receiver pushes
unsolicited state events on the same connection; the reader thread parses
them into a snapshot and notifies callbacks.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime

from denon_controller.transport.http import ReceiverError, _validate_private_destination

TELNET_PORT = 23

# Graphic EQ band labels, 63 Hz to 16 kHz (9 bands).
EQ_BANDS = ("63 Hz", "125 Hz", "250 Hz", "500 Hz", "1 kHz", "2 kHz", "4 kHz", "8 kHz", "16 kHz")

# Graphic EQ speaker groups as emitted in SSAEQLRS lines.
EQ_GROUPS = {
    "FRO": "Front",
    "CEN": "Center",
    "SUR": "Surround",
    "SBK": "Surround Back",
    "FRH": "Front Height",
    "TFR": "Top Front",
    "TPM": "Top Middle",
    "FRD": "Front Dolby",
    "SUD": "Surround Dolby",
}

# Channel trim codes as emitted in CV lines.
TRIM_CHANNELS = {
    "FL": "Front L",
    "FR": "Front R",
    "C": "Center",
    "SW": "Subwoofer",
    "SL": "Surround L",
    "SR": "Surround R",
    "SDL": "Surround Dolby L",
    "SDR": "Surround Dolby R",
}

READ_ONLY_QUERIES = (
    "PW?",
    "ZM?",
    "Z2?",
    "MV?",
    "MU?",
    "SI?",
    "MS?",
    "CV?",
    "PSGEQ ?",
    "SSAEQLRS ?",
    "PSTONE CTRL ?",
)

# Periodic/unsolicited status noise that diagnostics may hide by default.
NOISE_PREFIXES = ("SSSPC", "OPSTS", "OPCLA", "OPINF", "SSECO", "SSINFAISSIG", "DCAUTO")


def level_to_db(raw: str) -> float:
    """Decode a Denon level ('57' -> +7.0, '545' -> +4.5, '50' -> 0.0)."""
    value = int(raw)
    if len(raw) >= 3:
        return value / 10 - 50.0
    return float(value - 50)


def db_to_level(db: float) -> str:
    """Encode dB into Denon level text (half-dB steps become three digits)."""
    half_steps = round(db * 2) / 2
    scaled = half_steps + 50.0
    if scaled.is_integer():
        return f"{int(scaled):02d}"
    return f"{int(scaled * 10):03d}"


def db_to_eq_level(db: float) -> str:
    """Encode dB into the always-three-digit graphic EQ band format."""
    half_steps = round(db * 2) / 2
    return f"{int((half_steps + 50.0) * 10):03d}"


def parse_volume(raw: str) -> float:
    """Decode a main-volume payload ('52' -> 52.0, '525' -> 52.5)."""
    if len(raw) >= 3:
        return int(raw) / 10
    return float(int(raw))


def format_volume_command(volume: float) -> str:
    """Encode an absolute main-volume command on the 0-98 receiver scale."""
    half_steps = round(volume * 2) / 2
    if not 0 <= half_steps <= 98:
        raise ValueError("Volume must be between 0 and 98")
    if half_steps.is_integer():
        return f"MV{int(half_steps):02d}"
    return f"MV{int(half_steps):02d}5"


@dataclass
class ReceiverSnapshot:
    """Mutable receiver state assembled from Telnet events."""

    connected: bool = False
    power_on: bool | None = None
    main_zone_on: bool | None = None
    zone2_on: bool | None = None
    volume: float | None = None
    volume_max: float | None = None
    muted: bool | None = None
    input_source: str | None = None
    sound_mode: str | None = None
    sample_rate: str | None = None
    geq_on: bool | None = None
    multeq: str | None = None
    tone_bass_db: float | None = None
    tone_treble_db: float | None = None
    trims_db: dict[str, float] = field(default_factory=dict)
    eq_bands_db: dict[str, list[float]] = field(default_factory=dict)
    updated_at: datetime | None = None

    def copy(self) -> ReceiverSnapshot:
        return replace(
            self,
            trims_db=dict(self.trims_db),
            eq_bands_db={k: list(v) for k, v in self.eq_bands_db.items()},
        )


def apply_line(snapshot: ReceiverSnapshot, line: str) -> bool:
    """Apply one receiver response/event line. Returns True when state changed."""
    before = (
        snapshot.power_on,
        snapshot.main_zone_on,
        snapshot.zone2_on,
        snapshot.volume,
        snapshot.volume_max,
        snapshot.muted,
        snapshot.input_source,
        snapshot.sound_mode,
        snapshot.sample_rate,
        snapshot.geq_on,
        snapshot.multeq,
        snapshot.tone_bass_db,
        snapshot.tone_treble_db,
        tuple(sorted(snapshot.trims_db.items())),
        tuple(sorted((k, tuple(v)) for k, v in snapshot.eq_bands_db.items())),
    )
    if line == "PWON":
        snapshot.power_on = True
    elif line == "PWSTANDBY":
        snapshot.power_on = False
    elif line == "ZMON":
        snapshot.main_zone_on = True
    elif line == "ZMOFF":
        snapshot.main_zone_on = False
    elif line in ("Z2ON", "Z2OFF"):
        snapshot.zone2_on = line == "Z2ON"
    elif line.startswith("MVMAX "):
        snapshot.volume_max = parse_volume(line[6:].strip())
    elif line.startswith("MV") and line[2:].isdigit():
        snapshot.volume = parse_volume(line[2:])
    elif line in ("MUON", "MUOFF"):
        snapshot.muted = line == "MUON"
    elif line.startswith("SI"):
        snapshot.input_source = line[2:]
    elif line.startswith("MS"):
        snapshot.sound_mode = line[2:]
    elif line.startswith("SSINFAISFSV "):
        snapshot.sample_rate = line[12:].strip()
    elif line == "PSGEQ ON":
        snapshot.geq_on = True
    elif line == "PSGEQ OFF":
        snapshot.geq_on = False
    elif line.startswith("PSMULTEQ:"):
        snapshot.multeq = line[9:]
    elif line.startswith("PSBAS "):
        snapshot.tone_bass_db = level_to_db(line[6:].strip())
    elif line.startswith("PSTRE "):
        snapshot.tone_treble_db = level_to_db(line[6:].strip())
    elif line.startswith("CV") and line != "CVEND":
        code, _, value = line[2:].partition(" ")
        if code in TRIM_CHANNELS and value.strip().isdigit():
            snapshot.trims_db[code] = level_to_db(value.strip())
    elif line.startswith("SSAEQLRS") and line != "SSAEQLRSEND":
        group, _, values = line[8:].partition(" ")
        parts = values.strip().split(":")
        if group in EQ_GROUPS and len(parts) == len(EQ_BANDS):
            try:
                snapshot.eq_bands_db[group] = [level_to_db(part) for part in parts]
            except ValueError:
                return False
    else:
        return False
    snapshot.updated_at = datetime.now().astimezone()
    after = (
        snapshot.power_on,
        snapshot.main_zone_on,
        snapshot.zone2_on,
        snapshot.volume,
        snapshot.volume_max,
        snapshot.muted,
        snapshot.input_source,
        snapshot.sound_mode,
        snapshot.sample_rate,
        snapshot.geq_on,
        snapshot.multeq,
        snapshot.tone_bass_db,
        snapshot.tone_treble_db,
        tuple(sorted(snapshot.trims_db.items())),
        tuple(sorted((k, tuple(v)) for k, v in snapshot.eq_bands_db.items())),
    )
    return after != before


class TelnetController:
    """Threaded Telnet connection with event listening and safe sends."""

    def __init__(
        self,
        host: str,
        port: int = TELNET_PORT,
        timeout: float = 5.0,
        on_line: Callable[[str], None] | None = None,
        on_state: Callable[[ReceiverSnapshot], None] | None = None,
        on_connection: Callable[[bool, str], None] | None = None,
    ) -> None:
        self.host = _validate_private_destination(host)
        if not 1 <= port <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        self.port = port
        self.timeout = timeout
        self.on_line = on_line
        self.on_state = on_state
        self.on_connection = on_connection
        self.snapshot = ReceiverSnapshot()
        self._sock: socket.socket | None = None
        self._send_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._stop = threading.Event()
        self._reader: threading.Thread | None = None
        self._last_send = 0.0

    def connect(self) -> None:
        if self._sock is not None:
            return
        try:
            self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        except OSError as exc:
            raise ReceiverError(f"Telnet connection failed: {exc}") from exc
        self._sock.settimeout(0.5)
        self._stop.clear()
        with self._state_lock:
            self.snapshot.connected = True
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        if self.on_connection is not None:
            self.on_connection(True, "Connected")
        threading.Thread(target=self.request_full_status, daemon=True).start()

    def disconnect(self) -> None:
        self._stop.set()
        sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        with self._state_lock:
            self.snapshot.connected = False
        if self.on_connection is not None:
            self.on_connection(False, "Disconnected")

    def send(self, command: str) -> None:
        """Send one command, rate limited to protect the receiver."""
        sock = self._sock
        if sock is None:
            raise ReceiverError("Not connected")
        with self._send_lock:
            delta = time.monotonic() - self._last_send
            if delta < 0.06:
                time.sleep(0.06 - delta)
            try:
                sock.sendall((command + "\r").encode("ascii"))
            except OSError as exc:
                raise ReceiverError(f"Send failed: {exc}") from exc
            self._last_send = time.monotonic()
        if self.on_line is not None:
            self.on_line(f"> {command}")

    def request_full_status(self) -> None:
        """Issue the read-only query set; responses arrive via the reader."""
        for query in READ_ONLY_QUERIES:
            if self._stop.is_set():
                return
            try:
                self.send(query)
            except ReceiverError:
                return
            time.sleep(0.15)

    def current_snapshot(self) -> ReceiverSnapshot:
        with self._state_lock:
            return self.snapshot.copy()

    def _read_loop(self) -> None:
        buffer = ""
        while not self._stop.is_set():
            sock = self._sock
            if sock is None:
                break
            try:
                data = sock.recv(4096)
            except TimeoutError:
                continue
            except OSError:
                break
            if not data:
                break
            buffer += data.decode("ascii", "replace")
            while "\r" in buffer:
                line, buffer = buffer.split("\r", 1)
                if not line:
                    continue
                if self.on_line is not None:
                    self.on_line(f"< {line}")
                with self._state_lock:
                    changed = apply_line(self.snapshot, line)
                    snapshot = self.snapshot.copy() if changed else None
                if snapshot is not None and self.on_state is not None:
                    self.on_state(snapshot)
        if not self._stop.is_set():
            with self._state_lock:
                self.snapshot.connected = False
            if self.on_connection is not None:
                self.on_connection(False, "Connection lost")
