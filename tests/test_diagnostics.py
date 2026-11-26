import json

import pytest

from denon_controller.app import main
from denon_controller.services.diagnostics import Diagnostics, sanitize


def test_sanitized_bounded_export(tmp_path):
    diagnostics = Diagnostics("avr.example")
    for _ in range(250):
        diagnostics.record("HTTP", "avr.example 192.0.2.1 http://private.example/path")
    diagnostics.record("TCP", "fd12:3456::1 aa:bb:cc:dd:ee:ff")
    path = tmp_path / "report.json"
    diagnostics.export(path)
    text = path.read_text()
    assert len(json.loads(text)["events"]) == 200
    assert "avr.example" not in text
    assert "192.0.2.1" not in text
    assert "fd12:3456::1" not in text
    assert "aa:bb:cc:dd:ee:ff" not in text
    assert "http://" not in text


def test_diagnostic_cli_is_read_only_by_default(capsys):
    assert main(["--simulate", "--diagnose"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["power_on"] == "Not requested"
    assert "system=False" in report["events"][-1]["result"]


def test_explicit_diagnostic_power_on(capsys, tmp_path):
    path = tmp_path / "report.json"
    assert main(["--simulate", "--diagnose", "--power-on", "--output", str(path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["power_on"] == "Confirmed by readback"
    assert report["simulation"] is True
    assert path.exists()


def test_power_on_flag_cannot_start_gui():
    with pytest.raises(SystemExit) as exc:
        main(["--power-on"])
    assert exc.value.code == 2


def test_ipv6_scope_redacted():
    assert sanitize("error fe80::1%eth0") == "error [address]"
