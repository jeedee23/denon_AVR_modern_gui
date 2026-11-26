import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from denon_controller.models import Connection
from denon_controller.settings import Settings
from denon_controller.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


def wait_for(predicate):
    for _ in range(150):
        QApplication.processEvents()
        if predicate():
            return
        QTest.qWait(20)
    pytest.fail("Qt operation did not complete within 3 seconds")


@pytest.fixture
def window(app):
    widget = MainWindow(Settings(), simulate=True)
    widget.show()
    wait_for(lambda: widget.state.connection == Connection.CONNECTED)
    yield widget
    widget.close()
    wait_for(lambda: widget.stopped)
    assert widget.thread.wait(1000)
    widget.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_simulation_opens_without_writes(window):
    assert window.tabs.count() == 7
    assert window.state.main.volume_db == -45
    assert window.worker.receiver.simulation.sent == []
    assert "SIMULATION" in window.heading.text()


def test_state_slider_updates_never_send_commands(window):
    spy = QSignalSpy(window.action_requested)
    window.overview.slider.setFocus()
    window.overview.slider.setValue(-80)
    window.update_state(window.state, [])
    QTest.keyClick(window.overview.slider, Qt.Key.Key_Right)
    QApplication.processEvents()
    assert spy.count() == 0
    assert window.worker.receiver.simulation.sent == []


def test_power_click_and_readback(window):
    QTest.mouseClick(window.overview.power_on, Qt.MouseButton.LeftButton)
    wait_for(lambda: window.state.main.power is True)
    assert window.worker.receiver.simulation.sent == ["PWON"]
    assert "Confirmed by state readback" in window.overview.outcome.text()


def test_disconnect_reconnect_sends_no_power_command(window):
    window.disconnect_receiver()
    wait_for(lambda: window.worker.receiver is None)
    assert window.state.connection == Connection.DISCONNECTED
    assert not window.overview.up.isEnabled()
    window.connect_receiver()
    wait_for(lambda: window.state.connection == Connection.CONNECTED)
    assert window.worker.receiver.simulation.sent == []


def test_freshness_refresh_preserves_input_selection(window):
    window.sources.inputs.setCurrentIndex(1)
    spy = QSignalSpy(window.sources.inputs.currentIndexChanged)
    window.update_state(window.state, [])
    assert window.sources.inputs.currentIndex() == 1
    assert spy.count() == 0
    assert window.worker.receiver.simulation.sent == []
