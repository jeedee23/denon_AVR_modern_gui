from __future__ import annotations

import math
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import StrEnum


class Connection(StrEnum):
    DISCONNECTED = "Disconnected"
    CONNECTING = "Connecting"
    CONNECTED = "Connected"
    OFFLINE = "Offline"


class Evidence(StrEnum):
    VERIFIED = "VERIFIED (owner)"
    OBSERVED = "Readback observed"
    PROPOSED = "UNVERIFIED / PROPOSED"
    UNSUPPORTED = "Not available"


@dataclass
class ZoneState:
    power: bool | None = None
    volume_db: float | None = None
    mute: bool | None = None
    source: str | None = None


@dataclass
class DeviceState:
    name: str = "Denon AVR-X3400H"
    connection: Connection = Connection.DISCONNECTED
    system_power: bool | None = None
    main: ZoneState = field(default_factory=ZoneState)
    zone2: ZoneState = field(default_factory=ZoneState)
    surround: str | None = None
    sources: dict[str, str] = field(default_factory=dict)
    protocol: str = "Not connected"
    last_seen: float | None = None
    roundtrip_ms: float | None = None
    last_error: str = ""
    outcome: str = "No commands sent"
    observed_at: dict[str, float] = field(default_factory=dict)

    def is_fresh(self, attribute: str, max_age: float) -> bool:
        observed = self.observed_at.get(attribute)
        return observed is not None and time.monotonic() - observed <= max_age


def _observe(state: DeviceState, target: DeviceState | ZoneState, attribute: str, value) -> None:
    setattr(target, attribute, value)
    prefix = "" if target is state else ("main." if target is state.main else "zone2.")
    state.observed_at[prefix + attribute] = time.monotonic()


def encode_volume(db: float) -> str:
    if not math.isfinite(db) or not -80 <= db <= 18 or db * 2 != int(db * 2):
        raise ValueError("Volume must be -80 to +18 dB in half-dB steps.")
    value = db + 80
    return f"{int(value):02d}" + ("5" if value % 1 else "")


def decode_volume(raw: str) -> float:
    if not re.fullmatch(r"\d{2}5?", raw):
        raise ValueError("Invalid Denon volume encoding.")
    value = int(raw[:2]) - 80 + (0.5 if len(raw) == 3 else 0)
    if not -80 <= value <= 18:
        raise ValueError("Volume outside receiver bounds.")
    return value


def apply_event(state: DeviceState, line: str) -> bool:
    """Apply only recognized state lines, never command echoes such as MVUP."""
    for prefix, target, attribute in (
        ("PW", state, "system_power"),
        ("ZM", state.main, "power"),
        ("MU", state.main, "mute"),
        ("Z2MU", state.zone2, "mute"),
        ("Z2", state.zone2, "power"),
    ):
        if line.startswith(prefix):
            value = line[len(prefix) :]
            if value in ("ON", "OFF", "STANDBY"):
                _observe(state, target, attribute, value == "ON")
                return True
    for prefix, zone in (("MV", state.main), ("Z2", state.zone2)):
        if line.startswith(prefix):
            try:
                _observe(state, zone, "volume_db", decode_volume(line[len(prefix) :]))
                return True
            except ValueError:
                pass
    for prefix, target, attribute in (
        ("SI", state.main, "source"),
        ("MS", state, "surround"),
    ):
        value = line[len(prefix) :]
        if (
            line.startswith(prefix)
            and value != "?"
            and re.fullmatch(r"[A-Z0-9 /+_.:-]{1,60}", value)
        ):
            _observe(state, target, attribute, value)
            return True
    return False


def parse_xml(data: bytes) -> ET.Element:
    if (
        len(data) > 65536
        or b"\x00" in data
        or b"<!DOCTYPE" in data.upper()
        or b"<!ENTITY" in data.upper()
    ):
        raise ValueError("Unsafe or oversized XML response.")
    return ET.fromstring(data)


def apply_status_xml(state: DeviceState, data: bytes, zone: str = "main") -> bool:
    root = parse_xml(data)
    target = state.main if zone == "main" else state.zone2
    changed = False
    for tag, attribute in (("Power", "power"), ("Mute", "mute")):
        value = root.findtext(f".//{tag}/value")
        if value and value.upper() in ("ON", "OFF", "STANDBY"):
            _observe(state, target, attribute, value.upper() == "ON")
            changed = True
    volume = root.findtext(".//MasterVolume/value")
    if volume:
        try:
            number = float(volume)
            if math.isfinite(number) and -80 <= number <= 18:
                _observe(state, target, "volume_db", number)
                changed = True
        except ValueError:
            pass
    for tag, attribute in (("InputFuncSelect", "source"), ("selectSurround", "surround")):
        value = root.findtext(f".//{tag}/value")
        if value and len(value) <= 100:
            if attribute == "surround":
                if zone == "main":
                    _observe(state, state, "surround", value.strip())
            else:
                _observe(state, target, "source", value.strip())
            changed = True
    # Main-zone XML Power is ZM state, not evidence for system PW.
    return changed


def apply_device_xml(state: DeviceState, data: bytes) -> None:
    root = parse_xml(data)
    name = root.findtext(".//FriendlyName") or root.findtext(".//ModelName")
    if name:
        state.name = name.strip()[:100]
    sources = {}
    for entry in root.findall(".//InputSource"):
        token = entry.findtext("FuncName") or ""
        label = entry.findtext("Rename") or entry.findtext("DefaultName") or token
        if re.fullmatch(r"[A-Z0-9 /-]{1,20}", token):
            sources[token] = label.strip()[:80]
    state.sources = sources
