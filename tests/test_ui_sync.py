import os
from unittest.mock import patch

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from denon_controller.services.receiver import ReceiverService
from denon_controller.settings import Settings
from denon_controller.transport.discovery import DiscoveredReceiver, DiscoveryResult
from denon_controller.transport.simulation import SimulatedReceiver
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


def test_ui_starts_polling_and_refreshes_after_power_on() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(
        Settings(host="192.168.1.20", poll_interval_seconds=1, auto_connect=True),
        simulated=True,
    )
    window.show()

    assert _wait_until(lambda: window.connection_label.text() == "Connected")
    assert window.timer.isActive()
    assert window.power_label.text() == "Standby"

    window.power_button.click()
    assert _wait_until(lambda: window.power_label.text() == "On")
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


def test_scan_finds_single_receiver_without_automatically_connecting_when_disabled() -> None:
    app = QApplication.instance() or QApplication([])
    result = DiscoveryResult((DiscoveredReceiver("192.168.1.20", "Living Room", "AVR-X3400H"),))
    with patch("denon_controller.ui.main_window.discover_receivers", return_value=result):
        window = MainWindow(Settings(auto_connect=False))
        window.show()
        assert _wait_until(lambda: window.host_edit.text() == "192.168.1.20")
        assert window.connection_label.text() == "Offline"
        window.close()
        app.processEvents()


def test_startup_scans_and_connects_saved_address_without_overwriting_it() -> None:
    app = QApplication.instance() or QApplication([])
    result = DiscoveryResult((DiscoveredReceiver("192.168.1.21", "Another AVR", "AVR"),))
    with (
        patch("denon_controller.ui.main_window.discover_receivers", return_value=result) as scan,
        patch.object(
            MainWindow, "_make_service", return_value=ReceiverService(SimulatedReceiver())
        ),
    ):
        window = MainWindow(Settings(host="192.168.1.20", auto_connect=True))
        window.show()
        assert _wait_until(lambda: window.connection_label.text() == "Connected")
        scan.assert_called_once()
        assert window.host_edit.text() == "192.168.1.20"
        window.close()
        app.processEvents()
