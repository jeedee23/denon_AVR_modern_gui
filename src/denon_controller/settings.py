"""Application settings and per-user configuration paths."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    host: str = ""
    http_port: int = 8080
    poll_interval_seconds: int = 3
    request_timeout_seconds: float = 3.0
    auto_connect: bool = True
    volume_ceiling_db: float = -30.0

    def __post_init__(self) -> None:
        if not 1 <= self.http_port <= 65535:
            raise ValueError("HTTP port must be between 1 and 65535")
        if not 1 <= self.poll_interval_seconds <= 60:
            raise ValueError("Poll interval must be between 1 and 60 seconds")
        if not 0.2 <= self.request_timeout_seconds <= 15:
            raise ValueError("Request timeout must be between 0.2 and 15 seconds")
        if self.volume_ceiling_db > -0.5:
            raise ValueError("Volume ceiling must be -0.5 dB or quieter")


def config_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif os.uname().sysname == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "denon-avr-controller" / "config.toml"


def load_settings(path: Path | None = None) -> Settings:
    target = path or config_path()
    if not target.exists():
        return Settings()
    with target.open("rb") as config_file:
        data = tomllib.load(config_file)
    receiver = data.get("receiver", {})
    return Settings(
        host=str(receiver.get("host", "")),
        http_port=int(receiver.get("http_port", 8080)),
        poll_interval_seconds=int(receiver.get("poll_interval_seconds", 3)),
        request_timeout_seconds=float(receiver.get("request_timeout_seconds", 3)),
        auto_connect=bool(receiver.get("auto_connect", True)),
        volume_ceiling_db=float(receiver.get("volume_ceiling_db", -30.0)),
    )


def save_settings(settings: Settings, path: Path | None = None) -> Path:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "[receiver]\n"
        f'host = "{settings.host}"\n'
        f"http_port = {settings.http_port}\n"
        f"poll_interval_seconds = {settings.poll_interval_seconds}\n"
        f"request_timeout_seconds = {settings.request_timeout_seconds}\n"
        f"auto_connect = {str(settings.auto_connect).lower()}\n"
        f"volume_ceiling_db = {settings.volume_ceiling_db}\n"
    )
    target.write_text(content, encoding="utf-8")
    return target
