"""Named sound profiles: volume, sound mode, graphic EQ, and channel trims.

Profiles are stored per user next to the app configuration. Applying a
profile only sends commands verified on the owner's receiver, and the
volume is always clamped to the configured safety limit.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from denon_controller.settings import config_path
from denon_controller.transport.telnet import (
    EQ_BANDS,
    EQ_GROUPS,
    TRIM_CHANNELS,
    ReceiverSnapshot,
    db_to_eq_level,
    db_to_level,
    format_volume_command,
)


@dataclass(frozen=True, slots=True)
class Profile:
    name: str
    volume: float | None = None
    sound_mode: str | None = None
    geq_on: bool | None = None
    trims_db: dict[str, float] = field(default_factory=dict)
    eq_bands_db: dict[str, list[float]] = field(default_factory=dict)


def profiles_path() -> Path:
    return config_path().parent / "profiles.json"


def load_store(path: Path | None = None) -> dict:
    target = path or profiles_path()
    if not target.exists():
        return {"last": None, "auto_apply": True, "profiles": {}}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"last": None, "auto_apply": True, "profiles": {}}
    return {
        "last": data.get("last"),
        "auto_apply": bool(data.get("auto_apply", True)),
        "profiles": {
            name: raw for name, raw in data.get("profiles", {}).items() if isinstance(raw, dict)
        },
    }


def save_store(store: dict, path: Path | None = None) -> Path:
    target = path or profiles_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(store, indent=2), encoding="utf-8")
    return target


def profile_from_snapshot(name: str, snapshot: ReceiverSnapshot) -> Profile:
    return Profile(
        name=name,
        volume=snapshot.volume,
        sound_mode=snapshot.sound_mode,
        geq_on=snapshot.geq_on,
        trims_db={k: v for k, v in snapshot.trims_db.items() if k in TRIM_CHANNELS},
        eq_bands_db={
            group: list(bands)
            for group, bands in snapshot.eq_bands_db.items()
            if group in EQ_GROUPS and len(bands) == len(EQ_BANDS)
        },
    )


def profile_to_dict(profile: Profile) -> dict:
    return asdict(profile)


def profile_from_dict(name: str, data: dict) -> Profile:
    return Profile(
        name=name,
        volume=data.get("volume"),
        sound_mode=data.get("sound_mode"),
        geq_on=data.get("geq_on"),
        trims_db={
            k: float(v) for k, v in data.get("trims_db", {}).items() if k in TRIM_CHANNELS
        },
        eq_bands_db={
            group: [float(v) for v in bands]
            for group, bands in data.get("eq_bands_db", {}).items()
            if group in EQ_GROUPS and len(bands) == len(EQ_BANDS)
        },
    )


def apply_commands(profile: Profile, volume_limit: float) -> list[str]:
    """Ordered receiver commands to apply a profile, volume clamped to limit."""
    commands: list[str] = []
    if profile.volume is not None:
        commands.append(format_volume_command(min(profile.volume, volume_limit)))
    if profile.sound_mode:
        commands.append(f"MS{profile.sound_mode}")
    if profile.geq_on is not None:
        commands.append("PSGEQ ON" if profile.geq_on else "PSGEQ OFF")
    for code, db in profile.trims_db.items():
        commands.append(f"CV{code} {db_to_level(db)}")
    for group, bands in profile.eq_bands_db.items():
        encoded = ":".join(db_to_eq_level(db) for db in bands)
        commands.append(f"SSAEQLRS{group} {encoded}")
    return commands
