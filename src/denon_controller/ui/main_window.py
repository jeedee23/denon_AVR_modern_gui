"""Asynchronous Qt window for basic receiver monitoring and verified power-on."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from denon_controller.models import DeviceState
from denon_controller.services.receiver import ReceiverService
from denon_controller.settings import Settings, save_settings
from denon_controller.transport.discovery import DiscoveryResult, discover_receivers
from denon_controller.transport.http import HttpReceiver


class _WorkerSignals(QObject):
    finished = Signal(object, object)


class _Worker(QRunnable):
    def __init__(self, operation) -> None:
        super().__init__()
        self.operation = operation
        self.signals = _WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.finished.emit(self.operation(), None)
        except Exception as exc:
            self.signals.finished.emit(None, exc)


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, simulated: bool = False) -> None:
        super().__init__()
        self.settings = settings
        self.simulated = simulated
        self.pool = QThreadPool.globalInstance()
        self.service: ReceiverService | None = None
        self._busy = False
        self._workers: list[_Worker] = []
        self._pending_callback = None
        self._power_was_enabled = False
        self._startup_scan = not simulated
        self._build_ui()
        self.timer = QTimer(self)
        self.timer.setInterval(settings.poll_interval_seconds * 1000)
        self.timer.timeout.connect(self.refresh)
        if simulated and settings.auto_connect and settings.host:
            self.connect_receiver()
        elif not simulated:
            QTimer.singleShot(0, self.scan_receivers)

    def _build_ui(self) -> None:
        self.setWindowTitle("Denon AVR Controller")
        self.resize(760, 500)
        self.setMinimumSize(600, 380)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        header = QLabel("Denon AVR-X3400H")
        header.setStyleSheet("font-size: 24px; font-weight: 600;")
        layout.addWidget(header)

        form = QFormLayout()
        self.host_edit = QLineEdit(self.settings.host)
        self.host_edit.setPlaceholderText("Receiver IP address or local hostname")
        form.addRow("Receiver host:", self.host_edit)
        self.receivers_combo = QComboBox()
        self.receivers_combo.addItem("Select a discovered receiver", "")
        self.receivers_combo.currentIndexChanged.connect(self._select_receiver)
        form.addRow("Discovered receivers:", self.receivers_combo)
        self.discovery_label = QLabel("Not scanned")
        self.discovery_label.setWordWrap(True)
        form.addRow("Discovery:", self.discovery_label)
        self.auto_connect_box = QCheckBox("Connect and sync automatically on launch")
        self.auto_connect_box.setChecked(self.settings.auto_connect)
        form.addRow("Auto-connect:", self.auto_connect_box)
        self.poll_interval_spin = QSpinBox()
        self.poll_interval_spin.setRange(1, 60)
        self.poll_interval_spin.setSuffix(" seconds")
        self.poll_interval_spin.setValue(self.settings.poll_interval_seconds)
        form.addRow("Status polling:", self.poll_interval_spin)
        layout.addLayout(form)

        controls = QHBoxLayout()
        self.scan_button = QPushButton("Scan for Denon")
        self.scan_button.setToolTip("Search the local network using read-only UPnP discovery")
        self.scan_button.clicked.connect(self.scan_receivers)
        self.scan_button.setEnabled(not self.simulated)
        self.connect_button = QPushButton("Connect / refresh")
        self.connect_button.clicked.connect(self.connect_receiver)
        self.connect_button.setToolTip("Connect to the configured receiver and begin auto-sync")
        self.power_button = QPushButton("Power on")
        self.power_button.clicked.connect(self.power_on)
        self.power_button.setEnabled(False)
        self.power_button.setToolTip("Sends the owner-verified power-on command only")
        controls.addWidget(self.scan_button)
        controls.addWidget(self.connect_button)
        controls.addWidget(self.power_button)
        layout.addLayout(controls)

        self.connection_label = QLabel("Offline")
        self.power_label = QLabel("Unknown")
        self.input_label = QLabel("Not available")
        self.volume_label = QLabel("Not available")
        self.mute_label = QLabel("Not available")
        self.mode_label = QLabel("Not available")
        self.sync_label = QLabel("Not syncing")
        details = QFormLayout()
        details.addRow("Connection:", self.connection_label)
        details.addRow("Main Zone power:", self.power_label)
        details.addRow("Input:", self.input_label)
        details.addRow("Volume:", self.volume_label)
        details.addRow("Mute:", self.mute_label)
        details.addRow("Listening mode:", self.mode_label)
        details.addRow("Automatic sync:", self.sync_label)
        layout.addLayout(details)
        layout.addStretch(1)
        note = QLabel(
            "Only power-on is currently verified for this receiver. "
            "Status endpoint support and other controls remain unverified."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.setCentralWidget(central)

    def scan_receivers(self) -> None:
        if self._busy or self.simulated:
            return
        self.discovery_label.setText("Scanning the local network…")
        self._start_operation(discover_receivers, self._on_discovery)

    def _select_receiver(self) -> None:
        host = self.receivers_combo.currentData()
        if host:
            self.host_edit.setText(host)

    def _on_discovery(self, result: DiscoveryResult | None, error: Exception | None) -> None:
        startup = self._startup_scan
        self._startup_scan = False
        if error is not None:
            self.discovery_label.setText(f"Scan failed: {error}")
            if startup and self.auto_connect_box.isChecked() and self.host_edit.text().strip():
                self.connect_receiver()
            return
        assert result is not None
        self.receivers_combo.clear()
        self.receivers_combo.addItem("Select a discovered receiver", "")
        for receiver in result.receivers:
            name = receiver.name
            if receiver.model and receiver.model.lower() not in name.lower():
                name = f"{name} ({receiver.model})"
            self.receivers_combo.addItem(f"{name} — {receiver.host}", receiver.host)
        count = len(result.receivers)
        text = f"Found {count} Denon device(s)" if count else "No Denon found; enter IP manually"
        if result.failed_descriptions:
            text += f"; {result.failed_descriptions} device description(s) could not be read"
        self.discovery_label.setText(text)
        if count == 1 and not self.host_edit.text().strip():
            self.receivers_combo.setCurrentIndex(1)
            if self.auto_connect_box.isChecked():
                self.connect_receiver()
                return
        if startup and self.auto_connect_box.isChecked() and self.host_edit.text().strip():
            self.connect_receiver()

    def _make_service(self) -> ReceiverService:
        if self.simulated:
            from denon_controller.transport.simulation import SimulatedReceiver

            return ReceiverService(SimulatedReceiver())
        host = self.host_edit.text().strip()
        settings = Settings(
            host=host,
            http_port=self.settings.http_port,
            poll_interval_seconds=self.poll_interval_spin.value(),
            request_timeout_seconds=self.settings.request_timeout_seconds,
            auto_connect=self.auto_connect_box.isChecked(),
            volume_ceiling_db=self.settings.volume_ceiling_db,
        )
        save_settings(settings)
        self.settings = settings
        self.timer.setInterval(settings.poll_interval_seconds * 1000)
        return ReceiverService(
            HttpReceiver(host, settings.http_port, settings.request_timeout_seconds)
        )

    def connect_receiver(self) -> None:
        if self._busy:
            return
        try:
            self.service = self._make_service()
        except Exception as exc:
            self.connection_label.setText(f"Error: {exc}")
            self.sync_label.setText("Not syncing")
            return
        self.connection_label.setText("Connecting")
        self._start_operation(self.service.refresh, self._on_refresh)

    def refresh(self) -> None:
        if self._busy or self.service is None:
            return
        self.sync_label.setText("Syncing…")
        self._start_operation(self.service.refresh, self._on_refresh)

    def power_on(self) -> None:
        if self._busy or self.service is None:
            return
        self._start_operation(self.service.power_on, self._on_power_command)

    def _start_operation(self, operation, callback) -> None:
        self._busy = True
        self.connect_button.setEnabled(False)
        self.scan_button.setEnabled(False)
        self._power_was_enabled = self.power_button.isEnabled()
        self.power_button.setEnabled(False)
        self._pending_callback = callback
        worker = _Worker(operation)
        self._workers.append(worker)
        worker.signals.finished.connect(self._operation_finished)
        self.pool.start(worker)

    @Slot(object, object)
    def _operation_finished(self, result, error) -> None:
        worker = self.sender()
        self._workers = [item for item in self._workers if item.signals is not worker]
        self._busy = False
        self.connect_button.setEnabled(True)
        self.scan_button.setEnabled(not self.simulated)
        self.power_button.setEnabled(self._power_was_enabled)
        callback = self._pending_callback
        self._pending_callback = None
        if callback is not None:
            callback(result, error)

    def _on_refresh(self, state: DeviceState | None, error: Exception | None) -> None:
        if error is not None:
            self.connection_label.setText(f"Offline: {error}")
            self.sync_label.setText("Refresh failed; retrying automatically")
            self.power_button.setEnabled(False)
            if not self.timer.isActive():
                self.timer.start()
            return
        assert state is not None
        self.connection_label.setText("Connected" if state.connected else "Offline")
        self.power_label.setText(state.main_zone.power.value)
        self.input_label.setText(state.main_zone.input_source or "Not available")
        volume = state.main_zone.volume_db
        self.volume_label.setText(f"{volume:.1f} dB" if volume is not None else "Not available")
        mute = state.main_zone.muted
        if mute is True:
            self.mute_label.setText("Muted")
        elif mute is False:
            self.mute_label.setText("Not muted")
        else:
            self.mute_label.setText("Not available")
        self.mode_label.setText(state.surround_mode or "Not available")
        timestamp = state.updated_at or datetime.now().astimezone()
        self.sync_label.setText(f"Updated {timestamp.strftime('%H:%M:%S')} — {state.status_detail}")
        self.power_button.setEnabled(True)
        self.timer.start()

    def _on_power_command(self, _result, error: Exception | None) -> None:
        if error is not None:
            self.connection_label.setText(f"Error: {error}")
            return
        self.connection_label.setText("Power-on sent; awaiting confirmation")
        self.refresh()
