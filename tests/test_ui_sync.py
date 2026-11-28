import os
from unittest.mock import patch

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from denon_controller.settings import Settings
from denon_controller.transport.discovery import DiscoveredReceiver, DiscoveryResult
from denon_controller.ui.main_window import MainWindow

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _wait_until(predicate, timeout_ms: int = 2_000) -> bool:
    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: loop.quit() if predicate() else None)
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    timer.start()
    deadline.start(timeout_ms)
    loop.exec()
    timer.stop()
    return predicate()


def test_simulated_connection_populates_live_state() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(Settings(host="192.168.1.20"), simulated=True)
    window.show()

    assert _wait_until(lambda: "Connected" in window.connection_label.text())
    assert _wait_until(lambda: window.power_label.text() == "Standby")
    assert window.input_label.text() == "SAT/CBL"
    assert window.status_volume_label.text().startswith("45.0")

    window.power_on_button.click()
    assert _wait_until(lambda: window.power_label.text() == "On")
    assert window.main_zone_label.text() == "On"
    # Zone 2 follows one second after power on.
    assert _wait_until(lambda: window.zone2_label.text() == "On", timeout_ms=3_000)

    window._enter_standby()
    assert _wait_until(lambda: window.power_label.text() == "Standby")
    assert window.main_zone_label.text() == "Off"
    assert window.zone2_label.text() == "Off"
    window.close()
    app.processEvents()


def test_volume_step_respects_safety_limit() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(Settings(host="192.168.1.20", volume_ceiling_db=-30.0), simulated=True)
    window.show()
    assert _wait_until(lambda: window.controller is not None)
    assert _wait_until(lambda: window.controller.current_snapshot().volume == 45.0)

    window.step_volume(+5)
    assert _wait_until(lambda: window.controller.current_snapshot().volume == 50.0)
    window.step_volume(+5)  # ceiling raw = 80 - 30 = 50 -> must not exceed
    assert window.controller.current_snapshot().volume == 50.0
    window.close()
    app.processEvents()


def test_equalizer_tab_tracks_simulated_eq_events() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(Settings(host="192.168.1.20"), simulated=True)
    window.show()
    assert _wait_until(lambda: window.controller is not None)
    # Wait for the initial full-status emission so it cannot overwrite the event below.
    assert _wait_until(lambda: "FRO" in window.controller.current_snapshot().eq_bands_db)

    window.controller.send("SSAEQLRSFRO 465:465:470:495:560:385:365:400:370")
    app.processEvents()
    assert _wait_until(
        lambda: window.equalizer_tab.band_sliders[4].value() == 12  # +6.0 dB -> 12 half-steps
    )
    window.close()
    app.processEvents()


def test_equalizer_offers_real_groups_with_isolate_and_all() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(Settings(host="192.168.1.20"), simulated=True)
    window.show()
    assert _wait_until(lambda: window.controller is not None)
    assert _wait_until(lambda: "FL" in window.controller.current_snapshot().trims_db)
    app.processEvents()

    tab = window.equalizer_tab
    combo = tab.group_combo
    # Simulated layout mirrors the owner's: Front/Center/Surround front/Surround back + All.
    assert [combo.itemData(i) for i in range(combo.count())] == [
        "FRO", "CEN", "SUR", "SUD", "ALL",
    ]
    assert [combo.itemText(i) for i in range(combo.count())] == [
        "Front", "Center", "Surround front", "Surround back", "All",
    ]

    # Isolate "Front": every other channel (incl. subwoofer) dims to -12 dB.
    combo.setCurrentIndex(0)
    tab.isolate_button.click()
    app.processEvents()
    trims = window.controller.current_snapshot().trims_db
    assert trims["FL"] == 0.0 and trims["FR"] == 0.0
    assert all(trims[code] == -12.0 for code in ("C", "SW", "SL", "SR", "SDL", "SDR"))

    # Switching group while isolated moves the dim set.
    combo.setCurrentIndex(1)  # Center
    app.processEvents()
    trims = window.controller.current_snapshot().trims_db
    assert trims["C"] == 0.0
    assert trims["FL"] == -12.0 and trims["FR"] == -12.0

    # Toggling off restores the captured baseline.
    tab.isolate_button.click()
    app.processEvents()
    trims = window.controller.current_snapshot().trims_db
    assert all(db == 0.0 for db in trims.values())

    # "All" writes the same band values to every fitted group and disables isolate.
    combo.setCurrentIndex(combo.count() - 1)
    app.processEvents()
    assert not tab.isolate_button.isEnabled()
    tab.band_sliders[0].setValue(6)  # +3.0 dB at 63 Hz
    tab.send_band_values()
    app.processEvents()
    bands = window.controller.current_snapshot().eq_bands_db
    assert all(bands[group][0] == 3.0 for group in ("FRO", "CEN", "SUR", "SUD"))
    window.close()
    app.processEvents()


def test_scan_offers_multiple_receivers_for_explicit_selection() -> None:
    app = QApplication.instance() or QApplication([])
    result = DiscoveryResult(
        (
            DiscoveredReceiver("192.168.1.20", "Living Room", "AVR-X3400H"),
            DiscoveredReceiver("192.168.1.21", "Bedroom", "AVR-X1000"),
        )
    )
    with patch("denon_controller.ui.main_window.discover_receivers", return_value=result):
        window = MainWindow(Settings(auto_connect=False))
        window.show()
        assert _wait_until(lambda: "Found 2" in window.discovery_label.text())
        assert window.host_edit.text() == ""
        window.receivers_combo.setCurrentIndex(2)
        assert window.host_edit.text() == "192.168.1.21"
        window.close()
        app.processEvents()
