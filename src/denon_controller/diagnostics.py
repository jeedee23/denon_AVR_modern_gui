"""Non-destructive command-line connectivity check."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

from denon_controller.settings import load_settings
from denon_controller.transport.http import HttpReceiver, ReceiverError


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Denon AVR HTTP status connectivity")
    parser.add_argument("--host", help="Receiver private IP address or hostname")
    parser.add_argument("--port", type=int, help="Receiver HTTP port (default: 8080)")
    parser.add_argument(
        "--power-on",
        action="store_true",
        help="Send the owner-verified PWON command (changes receiver power)",
    )
    args = parser.parse_args()
    settings = load_settings()
    host = args.host or settings.host
    if not host:
        parser.error("Provide --host or configure a receiver host in the user config")
    port = args.port or settings.http_port
    try:
        receiver = HttpReceiver(host, port, settings.request_timeout_seconds)
        if args.power_on:
            receiver.power_on()
            print("Power-on command sent; awaiting status confirmation.")
        state = receiver.get_main_zone_status()
        report = {
            "checked_at": datetime.now().astimezone().isoformat(),
            "connected": state.connected,
            "main_zone_power": state.main_zone.power.value,
            "input": state.main_zone.input_source,
            "volume_db": state.main_zone.volume_db,
            "status": state.status_detail,
        }
        print(json.dumps(report, indent=2))
        return 0
    except (ReceiverError, ValueError) as exc:
        print(f"Diagnostic failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
