from __future__ import annotations

import math
import os
import re
import sys
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path


def config_path() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "denon-controller" / "config.toml"


@dataclass(frozen=True)
class Settings:
    host: str = "receiver.local"
    http_port: int = 8080
    telnet_port: int = 23
    poll_interval: float = 5.0
    timeout: float = 1.5
    auto_connect: bool = False
    volume_ceiling: float = -30.0
    diagnostics_verbose: bool = False
    discovery_enabled: bool = False
    theme: str = "system"

    def __post_init__(self) -> None:
        if not isinstance(self.host, str) or not re.fullmatch(r"[a-zA-Z0-9._:-]{1,253}", self.host):
            raise ValueError("Enter a hostname or IP address, not a URL.")
        for port in (self.http_port, self.telnet_port):
            if type(port) is not int or not 1 <= port <= 65535:
                raise ValueError("Ports must be integers between 1 and 65535.")
        for name, low, high in (
            ("poll_interval", 2, 120),
            ("timeout", 0.2, 5),
            ("volume_ceiling", -80, 0),
        ):
            value = getattr(self, name)
            if (
                type(value) not in (int, float)
                or not math.isfinite(value)
                or not low <= value <= high
            ):
                raise ValueError(f"{name} must be between {low} and {high}.")
        for name in ("auto_connect", "diagnostics_verbose", "discovery_enabled"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be true or false.")
        if self.theme not in ("system", "light", "dark"):
            raise ValueError("Unknown theme.")

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        path = path or config_path()
        if not path.exists():
            return cls()
        with path.open("rb") as stream:
            return cls(**tomllib.load(stream))

    def save(self, path: Path | None = None) -> None:
        path = path or config_path()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        lines = []
        for key, value in asdict(self).items():
            if isinstance(value, bool):
                literal = str(value).lower()
            elif isinstance(value, str):
                literal = f'"{value}"'
            else:
                literal = str(value)
            lines.append(f"{key} = {literal}\n")
        temporary = path.with_suffix(".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                os.chmod(temporary, 0o600)
                stream.writelines(lines)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
