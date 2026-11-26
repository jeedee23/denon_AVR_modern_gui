from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from denon_controller.models import DeviceState, apply_event, apply_status_xml
from denon_controller.services.diagnostics import Diagnostics
from denon_controller.services.receiver import NETWORK_ERRORS
from denon_controller.settings import Settings
from denon_controller.transport.http import STATUS_PATHS, HttpTransport, private_address
from denon_controller.transport.simulation import SimulationTransport
from denon_controller.transport.telnet import TelnetTransport


def diagnose(
    settings: Settings,
    *,
    telnet: bool = False,
    power_on: bool = False,
    simulate: bool = False,
    output: Path | None = None,
) -> int:
    """Explicit diagnostic session: never writes unless power_on was requested."""
    diagnostics = Diagnostics(settings.host)
    state = DeviceState()
    http: HttpTransport | None = None
    tcp: TelnetTransport | None = None
    simulation = SimulationTransport() if simulate else None
    observed = False
    try:
        if simulation:
            if power_on:
                simulation.send("PWON")
                diagnostics.record("Power ON", "Sent, awaiting confirmation")
            simulation.populate(state)
            observed = True
        else:
            address = private_address(settings.host, timeout=settings.timeout)
            http = HttpTransport(settings, address)
            if power_on:
                try:
                    http.send("PWON")
                    diagnostics.record("Power ON", "Sent, awaiting confirmation")
                except NETWORK_ERRORS:
                    diagnostics.record("Power ON", "Indeterminate send; never retried")
            for path in STATUS_PATHS:
                try:
                    if apply_status_xml(state, http.get(path)):
                        diagnostics.record("HTTP status", f"Recognized readback from {path}")
                        observed = True
                        break
                    diagnostics.record("HTTP status", "HTTP 200 without recognized state")
                except NETWORK_ERRORS as exc:
                    diagnostics.record("HTTP status", str(exc))
            if telnet:
                tcp = TelnetTransport(settings, address)
                try:
                    tcp.connect()
                    for line in tcp.query():
                        observed = apply_event(state, line) or observed
                    diagnostics.record("TCP query", "Read-only query complete")
                except NETWORK_ERRORS as exc:
                    diagnostics.record("TCP query", str(exc))
        diagnostics.record(
            "Parsed status",
            f"system={state.system_power}; main={state.main.power}; "
            f"volume={state.main.volume_db}; mute={state.main.mute}",
        )
    except NETWORK_ERRORS as exc:
        diagnostics.record("Offline / error", str(exc))
    finally:
        for transport in (http, tcp, simulation):
            if transport:
                transport.close()
    confirmed = power_on and (state.system_power is True or state.main.power is True)
    result = {
        "simulation": simulate,
        "status": "Readback observed" if observed else "Offline / unrecognized status",
        "power_on": (
            "Confirmed by readback"
            if confirmed
            else "Sent or indeterminate; awaiting confirmation"
            if power_on
            else "Not requested"
        ),
        "firmware": "Not available",
        "events": [vars(event) for event in diagnostics.events],
    }
    print(json.dumps(result, indent=2))
    if output:
        diagnostics.export(output)
    return 0 if observed and (not power_on or confirmed) else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local-only native Denon AVR controller")
    parser.add_argument("--simulate", action="store_true", help="No network I/O; synthetic AVR")
    parser.add_argument("--config", type=Path, help="Override per-user TOML config file")
    parser.add_argument("--host", help="Configured private LAN receiver hostname or IP")
    parser.add_argument("--http-port", type=int, help="HTTP control port (default 8080)")
    parser.add_argument("--diagnose", action="store_true", help="Read-only diagnostics, no GUI")
    parser.add_argument("--telnet", action="store_true", help="Also query TCP during --diagnose")
    parser.add_argument("--power-on", action="store_true", help="Explicit diagnostic PWON opt-in")
    parser.add_argument("--output", type=Path, help="Explicit sanitized diagnostic JSON export")
    args = parser.parse_args(argv)
    if (args.telnet or args.power_on or args.output) and not args.diagnose:
        parser.error("--telnet, --power-on and --output require --diagnose")
    try:
        settings = Settings.load(args.config)
        overrides = {}
        if args.host is not None:
            overrides["host"] = args.host
        if args.http_port is not None:
            overrides["http_port"] = args.http_port
        settings = replace(settings, **overrides)
    except (OSError, ValueError, TypeError) as exc:
        parser.error(f"Invalid settings: {exc}")
    if args.diagnose:
        try:
            return diagnose(
                settings,
                telnet=args.telnet,
                power_on=args.power_on,
                simulate=args.simulate,
                output=args.output,
            )
        except OSError as exc:
            parser.error(f"Cannot export diagnostic file: {exc}")
    from PySide6.QtWidgets import QApplication

    from denon_controller.ui.main_window import MainWindow

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Denon AVR Controller")
    app.setOrganizationName("Denon Controller Community")
    window = MainWindow(settings, simulate=args.simulate)
    window.show()
    return app.exec()
