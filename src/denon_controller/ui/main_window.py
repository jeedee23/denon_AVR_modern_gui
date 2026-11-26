from __future__ import annotations

import copy
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QCloseEvent, QColor, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from denon_controller.models import Connection, DeviceState
from denon_controller.services.diagnostics import Diagnostics
from denon_controller.services.receiver import NETWORK_ERRORS, Receiver
from denon_controller.settings import Settings
from denon_controller.transport.discovery import DiscoveredDevice, discover
from denon_controller.ui.channels import Channels
from denon_controller.ui.diagnostics import DiagnosticsPage
from denon_controller.ui.overview import Overview, button, power_text
from denon_controller.ui.settings import SettingsPage
from denon_controller.ui.sound import Sound
from denon_controller.ui.sources import Sources
from denon_controller.ui.zones import Zones


def apply_theme(theme: str) -> None:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return
    if not app.property("denonStyleInitialized"):
        app.setStyle("Fusion")
        app.setProperty("denonStyleInitialized", True)
    palette = app.style().standardPalette()
    if theme == "dark":
        for role, color in (
            (QPalette.ColorRole.Window, "#202630"),
            (QPalette.ColorRole.WindowText, "#f3f5f7"),
            (QPalette.ColorRole.Base, "#151b23"),
            (QPalette.ColorRole.AlternateBase, "#252f3a"),
            (QPalette.ColorRole.Text, "#f3f5f7"),
            (QPalette.ColorRole.Button, "#303c4a"),
            (QPalette.ColorRole.ButtonText, "#f3f5f7"),
            (QPalette.ColorRole.Highlight, "#347bb8"),
            (QPalette.ColorRole.HighlightedText, "#ffffff"),
        ):
            palette.setColor(role, QColor(color))
    if theme == "system":
        app.setPalette(QPalette())
    else:
        app.setPalette(palette)
    app.setStyleSheet(
        "QWidget { font-size: 15px; } "
        "QPushButton, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { padding: 6px; } "
        "QPushButton:focus, QSlider:focus, QCheckBox:focus, QComboBox:focus { "
        "border: 2px solid #399fe5; } "
        "QLabel#sectionTitle { font-size: 25px; font-weight: bold; } "
        "QTabWidget::pane { padding: 10px; }"
    )


class ReceiverWorker(QObject):
    changed = Signal(object, object)
    error = Signal(str)
    discovered = Signal(object)
    stopped = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.receiver: Receiver | None = None
        self.poll_timer = QTimer(self)
        self.poll_timer.setSingleShot(True)
        self.poll_timer.timeout.connect(self.poll)
        self.event_timer = QTimer(self)
        self.event_timer.setInterval(200)
        self.event_timer.timeout.connect(self.events)
        self.failures = 0

    def publish(self) -> None:
        if self.receiver:
            self.changed.emit(
                copy.deepcopy(self.receiver.state), list(self.receiver.diagnostics.events)
            )

    @Slot(object, bool, object)
    def connect_receiver(
        self,
        settings: Settings,
        simulate: bool,
        cancelled: threading.Event,
    ) -> None:
        self.disconnect_receiver()
        self.receiver = Receiver(settings, simulate=simulate, cancelled=cancelled)
        self.receiver.state.connection = Connection.CONNECTING
        self.publish()
        self.failures = 0
        self.poll()
        self.event_timer.start()

    @Slot()
    def disconnect_receiver(self) -> None:
        self.poll_timer.stop()
        self.event_timer.stop()
        if self.receiver:
            self.receiver.close()
            self.publish()
        self.receiver = None

    @Slot()
    def poll(self) -> None:
        if not self.receiver:
            return
        state = self.receiver.poll()
        self.publish()
        if state.connection == Connection.OFFLINE:
            self.failures = min(5, self.failures + 1)
            interval = min(60, self.receiver.settings.poll_interval * 2**self.failures)
        else:
            self.failures = 0
            standby = state.system_power is False or state.main.power is False
            interval = max(30 if standby else 2, self.receiver.settings.poll_interval)
        if self.receiver.pending:
            interval = 1
        self.poll_timer.start(int(interval * 1000))

    @Slot()
    def events(self) -> None:
        if self.receiver and self.receiver.receive_events():
            self.publish()

    @Slot(str, object)
    def action(self, action: str, value: object) -> None:
        if not self.receiver:
            return
        try:
            self.receiver.action(action, value)
        except NETWORK_ERRORS as exc:
            self.error.emit(str(exc))
        self.publish()
        self.poll_timer.start(250)

    @Slot(bool)
    def enable_candidates(self, enabled: bool) -> None:
        if self.receiver:
            self.receiver.candidates_enabled = enabled or bool(self.receiver.simulation)

    @Slot(object)
    def discover(self, settings: Settings) -> None:
        if not settings.discovery_enabled:
            return
        try:
            self.discovered.emit(discover())
        except NETWORK_ERRORS as exc:
            self.error.emit(str(exc))

    @Slot()
    def shutdown(self) -> None:
        self.disconnect_receiver()
        self.stopped.emit()


class MainWindow(QMainWindow):
    connect_requested = Signal(object, bool, object)
    disconnect_requested = Signal()
    action_requested = Signal(str, object)
    candidate_requested = Signal(bool)
    refresh_requested = Signal()
    discovery_requested = Signal(object)
    shutdown_requested = Signal()

    def __init__(self, settings: Settings, *, simulate: bool = False) -> None:
        super().__init__()
        self.settings = settings
        self.simulate = simulate
        self.connected = False
        self.closing = False
        self.stopped = False
        self.state = DeviceState()
        self.log = Diagnostics(settings.host)
        self.cancelled = threading.Event()
        self.setWindowTitle("Denon AVR Controller" + (" — SIMULATION" if simulate else ""))
        self.resize(1060, 900)
        apply_theme(settings.theme)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        self.heading = QLabel("Denon AVR-X3400H")
        self.heading.setObjectName("sectionTitle")
        self.heading.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.heading)
        self.header_status = QLabel()
        self.header_status.setWordWrap(True)
        self.header_status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.header_status)
        row = QHBoxLayout()
        self.connect_button = button("Connect", "Connect and issue read-only status queries only.")
        self.disconnect_button = button("Disconnect", "Close connections; sends no power command.")
        self.refresh_button = button("Refresh status", "Read-only status refresh.")
        row.addWidget(self.connect_button)
        row.addWidget(self.disconnect_button)
        row.addWidget(self.refresh_button)
        layout.addLayout(row)
        self.tabs = QTabWidget()
        self.overview = Overview()
        self.sources = Sources()
        self.sound = Sound()
        self.zones = Zones()
        self.diagnostics = DiagnosticsPage()
        self.settings_page = SettingsPage(settings)
        for name, widget in (
            ("Overview", self.overview),
            ("Inputs", self.sources),
            ("Sound", self.sound),
            ("Channels", Channels()),
            ("Zones", self.zones),
            ("Diagnostics", self.diagnostics),
            ("Settings", self.settings_page),
        ):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(widget)
            self.tabs.addTab(scroll, name)
        layout.addWidget(self.tabs)
        self.message = QLabel(
            "Connect performs read-only queries. All hardware checks remain pending."
        )
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.message)
        self.thread = QThread(self)
        self.worker = ReceiverWorker()
        self.worker.moveToThread(self.thread)
        self.connect_requested.connect(self.worker.connect_receiver)
        self.disconnect_requested.connect(self.worker.disconnect_receiver)
        self.action_requested.connect(self.worker.action)
        self.candidate_requested.connect(self.worker.enable_candidates)
        self.refresh_requested.connect(self.worker.poll)
        self.discovery_requested.connect(self.worker.discover)
        self.shutdown_requested.connect(self.worker.shutdown)
        self.worker.changed.connect(self.update_state)
        self.worker.error.connect(self.message.setText)
        self.worker.discovered.connect(self.show_discovered)
        self.worker.stopped.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.finish_close)
        self.thread.start()
        self.freshness_timer = QTimer(self)
        self.freshness_timer.setInterval(1000)
        self.freshness_timer.timeout.connect(
            lambda: self.update_state(self.state, list(self.log.events))
        )
        self.freshness_timer.start()
        self.connect_button.clicked.connect(self.connect_receiver)
        self.disconnect_button.clicked.connect(self.disconnect_receiver)
        self.refresh_button.clicked.connect(self.refresh_requested)
        self.overview.action.connect(self.request_action)
        self.sources.action.connect(self.request_action)
        self.overview.standby.clicked.connect(lambda: self.request_action("standby", None))
        self.overview.candidate_changed.connect(self.enable_candidates)
        self.settings_page.save_requested.connect(self.save_settings)
        self.settings_page.error.connect(self.message.setText)
        self.settings_page.discovery_requested.connect(self.discovery_requested)
        self.diagnostics.refresh.connect(self.refresh_requested)
        self.diagnostics.export.connect(self.export_diagnostics)
        self.update_state(self.state, [])
        if simulate or settings.auto_connect:
            QTimer.singleShot(0, self.connect_receiver)

    @Slot()
    def connect_receiver(self) -> None:
        if self.connected:
            return
        self.connected = True
        self.state = DeviceState(connection=Connection.CONNECTING)
        self.update_state(self.state, [])
        self.cancelled = threading.Event()
        self.connect_requested.emit(self.settings, self.simulate, self.cancelled)

    @Slot()
    def disconnect_receiver(self) -> None:
        self.cancelled.set()
        self.connected = False
        self.overview.candidates.setChecked(False)
        self.disconnect_requested.emit()
        self.state = DeviceState()
        self.update_state(self.state, list(self.log.events))

    @Slot(bool)
    def enable_candidates(self, enabled: bool) -> None:
        if enabled and not self.simulate:
            answer = QMessageBox.warning(
                self,
                "Unverified controls",
                "Only HTTP Power ON is owner-verified. Basic writes are candidate Denon commands.\n"
                "Use low volume, supervise the receiver and check every readback. "
                "Enable this session?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.overview.candidates.setChecked(False)
                return
        self.candidate_requested.emit(enabled)
        self.update_state(self.state, list(self.log.events))

    @Slot(str, object)
    def request_action(self, action: str, value: object) -> None:
        if not self.connected:
            return
        if action == "standby" and not self.simulate:
            answer = QMessageBox.warning(
                self,
                "System standby",
                "Unverified whole-receiver standby can affect Zone 2. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.action_requested.emit(action, value)

    @Slot(object, object)
    def update_state(self, state: DeviceState, events: list) -> None:
        if not self.connected and state.connection != Connection.DISCONNECTED:
            return
        self.state = state
        self.log.events.clear()
        self.log.events.extend(events)
        candidates = self.simulate or self.overview.candidates.isChecked()
        enabled = candidates and self.connected and state.connection == Connection.CONNECTED
        self.heading.setText(state.name + (" · SIMULATION — no hardware" if self.simulate else ""))
        volume = (
            f"{state.main.volume_db:+.1f} dB" if state.main.volume_db is not None else "Unknown dB"
        )
        self.header_status.setText(
            f"{state.connection}  |  System: {power_text(state.system_power)}  |  "
            f"Main: {power_text(state.main.power)}  |  {state.main.source or 'Unknown input'}  |  "
            f"{state.surround or 'Unknown mode'}  |  {volume}  |  "
            f"Mute: {'Unknown' if state.main.mute is None else state.main.mute}"
        )
        self.connect_button.setEnabled(not self.connected)
        self.disconnect_button.setEnabled(self.connected)
        self.refresh_button.setEnabled(self.connected)
        self.diagnostics.probe.setEnabled(self.connected)
        self.settings_page.save.setEnabled(not self.connected)
        self.settings_page.discover.setEnabled(not self.connected)
        self.overview.candidates.setEnabled(self.connected and not self.simulate)
        self.overview.update_state(
            state,
            candidates=candidates,
            connected=self.connected,
            ceiling=self.settings.volume_ceiling,
            max_age=min(10, self.settings.poll_interval * 2),
        )
        self.sources.update_state(
            state,
            enabled and state.is_fresh("main.source", min(10, self.settings.poll_interval * 2)),
        )
        self.sound.update_state(state)
        self.zones.update_state(state)
        self.diagnostics.update_state(state, events)

    @Slot(object)
    def save_settings(self, settings: Settings) -> None:
        self.settings = settings
        self.log.host = settings.host
        apply_theme(settings.theme)
        self.message.setText("Settings saved. Connect when ready; no write commands sent.")
        self.update_state(self.state, list(self.log.events))

    @Slot(object)
    def show_discovered(self, devices: list[DiscoveredDevice]) -> None:
        if not devices:
            self.message.setText(
                "No local renderers found. Manual hostname/IP entry remains available."
            )
            return
        choices = [f"{device.host} — {device.description}" for device in devices]
        selected, accepted = QInputDialog.getItem(
            self,
            "Local discovery",
            "Select a renderer; identity must be checked by you.",
            choices,
            0,
            False,
        )
        if accepted:
            self.settings_page.host.setText(devices[choices.index(selected)].host)
            self.message.setText(
                "Selected host only; control port remains configurable. Save to use."
            )

    @Slot()
    def export_diagnostics(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export sanitized session", "diagnostic-session.json", "JSON (*.json)"
        )
        if filename:
            try:
                self.log.export(Path(filename))
                self.message.setText("Sanitized session exported. Review manually before sharing.")
            except OSError as exc:
                self.message.setText(str(exc))

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.stopped:
            event.accept()
            return
        event.ignore()
        if not self.closing:
            self.closing = True
            self.setEnabled(False)
            self.message.setText("Closing bounded network operations…")
            self.cancelled.set()
            self.shutdown_requested.emit()

    @Slot()
    def finish_close(self) -> None:
        self.stopped = True
        self.close()
