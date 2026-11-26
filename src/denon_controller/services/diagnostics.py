from __future__ import annotations

import ipaddress
import json
import re
from collections import deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


def sanitize(text: str, host: str = "") -> str:
    if host:
        text = text.replace(host, "[receiver]")
    text = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[address]", text)
    text = re.sub(r"\b(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}\b", "[hardware-address]", text)
    for candidate in re.findall(r"(?<!\w)[0-9a-fA-F:]*:[0-9a-fA-F:]+(?:%\w+)?", text):
        try:
            ipaddress.ip_address(candidate.split("%")[0])
        except ValueError:
            continue
        text = text.replace(candidate, "[address]")
    text = re.sub(r"https?://\S+", "[url]", text)
    return text


@dataclass(frozen=True)
class Event:
    timestamp: str
    category: str
    result: str


class Diagnostics:
    def __init__(self, host: str = "") -> None:
        self.host = host
        self.events: deque[Event] = deque(maxlen=200)

    def record(self, category: str, result: str) -> None:
        self.events.append(
            Event(
                datetime.now(UTC).isoformat(timespec="seconds"),
                sanitize(category, self.host),
                sanitize(result, self.host),
            )
        )

    def export(self, path: Path) -> None:
        document = {
            "format": 1,
            "firmware": "Not reported / not hardware verified",
            "notice": "Synthetic tests are not receiver certification. Review before sharing.",
            "events": [asdict(event) for event in self.events],
        }
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
