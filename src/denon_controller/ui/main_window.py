"""Main window: connection bar, main-zone strip, and dashboard/feature tabs.

High-contrast light theme for projection; realtime state via Telnet events.
"""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from denon_controller import profiles
from denon_controller.settings import Settings, save_settings
from denon_controller.transport.discovery import DiscoveryResult, discover_receivers
from denon_controller.transport.telnet import (
    ReceiverSnapshot,
    TelnetController,
    format_volume_command,
)
from denon_controller.ui.diagnostics import DiagnosticsTab
from denon_controller.ui.equalizer import EqualizerTab
from denon_controller.ui.speaker_test import SpeakerTestEngine, SpeakerTestTab
from denon_controller.ui.theme import ACCENTS, APP_STYLESHEET, Card

SOURCES = (
    ("CBL/SAT", "SISAT/CBL"),
    ("Blu-ray", "SIBD"),
    ("DVD", "SIDVD"),
    ("Game", "SIGAME"),
    ("Media Player", "SIMPLAY"),
    ("TV Audio", "SITV"),
    ("Tuner", "SITUNER"),
    ("CD", "SICD"),
    ("Phono", "SIPHONO"),
    ("HEOS / Net", "SINET"),
    ("Bluetooth", "SIBT"),
    ("AUX", "SIAUX1"),
)

SOUND_MODES = (
    ("Auto", "MSAUTO"),
    ("Stereo", "MSSTEREO"),
    ("Multi Ch Stereo", "MSMCH STEREO"),
    ("Dolby Surround", "MSDOLBY DIGITAL"),
    ("Neural:X", "MSDTS SURROUND"),
    ("Rock Arena", "MSROCK ARENA"),
    ("Jazz Club", "MSJAZZ CLUB"),
    ("Matrix", "MSMATRIX"),
    ("Virtual", "MSVIRTUAL"),
)


class TelnetBridge(QObject):
    """Marshals controller callbacks from worker threads onto the GUI thread."""

    line = Signal(str)
    state = Signal(object)
    connection = Signal(bool, str)


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
    profile_status = Signal(str)

    def __init__(self, settings: Settings, simulated: bool = False) -> None:
        super().__init__()
        self.settings = settings
        self.simulated = simulated
        self.pool = QThreadPool.globalInstance()
        self.controller = None
        self.bridge = TelnetBridge()
        self.bridge.line.connect(self._on_line)
        self.bridge.state.connect(self._on_state)
        self.bridge.connection.connect(self._on_connection)
        self._workers: list[_Worker] = []
        self._startup_scan = not simulated
        if simulated:
            self.profile_store = {"last": None, "auto_apply": True, "profiles": {}}
        else:
            self.profile_store = profiles.load_store()
        self._auto_apply_pending = False
        self._build_ui()
        self.profile_status.connect(self.profile_status_label.setText)
        if simulated:
            QTimer.singleShot(0, self.connect_receiver)
        else:
            QTimer.singleShot(0, self.scan_receivers)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        self.setWindowTitle("Denon AVR Controller")
        self.resize(1680, 1000)
        self.setStyleSheet(APP_STYLESHEET)
        root = QWidget(self)
        root.setObjectName("Root")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(12)
        layout.addWidget(self._build_connection_bar())
        layout.addWidget(self._build_main_zone_strip())

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_dashboard(), "Dashboard")
        self.speaker_engine = SpeakerTestEngine(self._controller_proxy())
        self.speaker_tab = SpeakerTestTab(self.speaker_engine)
        self.tabs.addTab(self.speaker_tab, "Speaker Test")
        self.equalizer_tab = EqualizerTab(self.send_command)
        self.tabs.addTab(self.equalizer_tab, "Equalizer")
        self.diagnostics_tab = DiagnosticsTab()
        self.tabs.addTab(self.diagnostics_tab, "Diagnostics")
        layout.addWidget(self.tabs, stretch=1)
        self.setCentralWidget(root)

    def _build_connection_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("Card")
        bar.setStyleSheet(
            f"QFrame#Card {{ background: #FFFFFF; border: 3px solid {ACCENTS['slate']};"
            f" border-radius: 14px; }}"
        )
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 10, 16, 10)
        title = QLabel("DENON AVR CONTROLLER")
        title.setObjectName("HeaderTitle")
        title.setStyleSheet("border: none;")
        row.addWidget(title)
        row.addStretch(1)
        self.host_edit = QLineEdit(self.settings.host)
        self.host_edit.setPlaceholderText("Receiver IP / hostname")
        self.host_edit.setMinimumWidth(220)
        row.addWidget(self.host_edit)
        self.receivers_combo = QComboBox()
        self.receivers_combo.addItem("Select a discovered receiver", "")
        self.receivers_combo.currentIndexChanged.connect(self._select_receiver)
        row.addWidget(self.receivers_combo)
        self.scan_button = QPushButton("Scan")
        self.scan_button.setToolTip("Read-only UPnP discovery on the local network")
        self.scan_button.clicked.connect(self.scan_receivers)
        self.scan_button.setEnabled(not self.simulated)
        row.addWidget(self.scan_button)
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.connect_receiver)
        row.addWidget(self.connect_button)
        self.auto_connect_box = QCheckBox("Auto-connect")
        self.auto_connect_box.setChecked(self.settings.auto_connect)
        row.addWidget(self.auto_connect_box)
        self.connection_label = QLabel("Offline")
        self.connection_label.setStyleSheet("font-weight: 800; border: none;")
        row.addWidget(self.connection_label)
        self.discovery_label = QLabel("Not scanned")
        self.discovery_label.setStyleSheet("border: none;")
        row.addWidget(self.discovery_label)
        return bar

    def _build_main_zone_strip(self) -> QWidget:
        strip = QFrame()
        strip.setObjectName("Card")
        strip.setStyleSheet(
            "QFrame#Card { background: #DCEBFF; border: 3px solid #0057C2;"
            " border-radius: 14px; }"
        )
        row = QHBoxLayout(strip)
        row.setContentsMargins(20, 12, 20, 12)
        zone_box = QVBoxLayout()
        zone_title = QLabel("MAIN ZONE")
        zone_title.setStyleSheet("font-weight: 800; color: #0057C2; border: none;")
        self.input_label = QLabel("—")
        self.input_label.setObjectName("BigValue")
        self.input_label.setStyleSheet("border: none;")
        self.mode_label = QLabel("Mode: —")
        self.mode_label.setStyleSheet("border: none;")
        zone_box.addWidget(zone_title)
        zone_box.addWidget(self.input_label)
        zone_box.addWidget(self.mode_label)
        row.addLayout(zone_box)
        row.addStretch(1)
        self.power_on_button = QPushButton("Power On")
        self.power_on_button.setObjectName("PowerOn")
        self.power_on_button.setMinimumSize(150, 64)
        self.power_on_button.setToolTip(
            "Powers on the main zone and Zone 2"
            " (Zone 2 command not yet verified on this receiver)"
        )
        self.power_on_button.clicked.connect(self.power_on_zones)
        row.addWidget(self.power_on_button)
        self.standby_button = QPushButton("Standby")
        self.standby_button.setObjectName("Standby")
        self.standby_button.setMinimumSize(150, 64)
        self.standby_button.clicked.connect(self.confirm_standby)
        row.addWidget(self.standby_button)
        self.mute_button = QPushButton("Mute")
        self.mute_button.setCheckable(True)
        self.mute_button.setMinimumSize(120, 64)
        self.mute_button.setToolTip("Candidate command — not yet verified on this receiver")
        self.mute_button.clicked.connect(self.toggle_mute)
        row.addWidget(self.mute_button)
        volume_box = QVBoxLayout()
        volume_caption = QLabel("Volume")
        volume_caption.setStyleSheet("font-weight: 700; border: none;")
        volume_caption.setAlignment(Qt.AlignHCenter)
        self.volume_value_label = QLabel("—")
        self.volume_value_label.setObjectName("BigValue")
        self.volume_value_label.setStyleSheet("border: none;")
        self.volume_value_label.setAlignment(Qt.AlignHCenter)
        volume_box.addWidget(volume_caption)
        volume_box.addWidget(self.volume_value_label)
        row.addLayout(volume_box)
        return strip

    def _build_dashboard(self) -> QWidget:
        page = QWidget()
        grid = QGridLayout(page)
        grid.setContentsMargins(4, 8, 4, 4)
        grid.setSpacing(14)
        grid.addWidget(self._build_volume_card(), 0, 0)
        grid.addWidget(self._build_source_card(), 0, 1)
        grid.addWidget(self._build_sound_mode_card(), 1, 0)
        audio_status = QVBoxLayout()
        audio_status.setSpacing(14)
        audio_status.addWidget(self._build_audio_card())
        audio_status.addWidget(self._build_status_card())
        holder = QWidget()
        holder.setLayout(audio_status)
        grid.addWidget(holder, 1, 1)
        grid.addWidget(self._build_profiles_card(), 2, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        return page

    def _build_volume_card(self) -> QWidget:
        card = Card("Volume", "blue")
        body = card.body()
        buttons = QHBoxLayout()
        for label, delta in (("−5", -5.0), ("−1", -1.0), ("+1", 1.0), ("+5", 5.0)):
            button = QPushButton(label)
            button.setMinimumHeight(48)
            button.clicked.connect(lambda _=False, d=delta: self.step_volume(d))
            buttons.addWidget(button)
        body.addLayout(buttons)
        slider_row = QHBoxLayout()
        self.volume_slider = QSlider(Qt.Horizontal)
        ceiling = self._volume_ceiling_raw()
        self.volume_slider.setRange(0, int(ceiling * 2))
        self.volume_slider.sliderReleased.connect(self._slider_volume)
        self.volume_slider_label = QLabel("—")
        self.volume_slider_label.setMinimumWidth(70)
        self.volume_slider.valueChanged.connect(
            lambda value: self.volume_slider_label.setText(f"{value / 2:.1f}")
        )
        slider_row.addWidget(self.volume_slider, stretch=1)
        slider_row.addWidget(self.volume_slider_label)
        body.addLayout(slider_row)
        limit_row = QHBoxLayout()
        limit_row.addWidget(QLabel("Safety limit (0–98):"))
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(20, 75)
        self.limit_spin.setValue(int(ceiling))
        self.limit_spin.valueChanged.connect(self._limit_changed)
        limit_row.addWidget(self.limit_spin)
        limit_row.addStretch(1)
        body.addLayout(limit_row)
        return card

    def _build_source_card(self) -> QWidget:
        card = Card("Source", "orange")
        grid = QGridLayout()
        grid.setSpacing(8)
        self.source_buttons: dict[str, QPushButton] = {}
        for index, (label, command) in enumerate(SOURCES):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setEnabled(False)
            button.setMinimumHeight(44)
            button.setToolTip("Input switching is not yet verified on this receiver")
            self.source_buttons[command[2:]] = button
            grid.addWidget(button, index // 4, index % 4)
        card.body().addLayout(grid)
        note = QLabel("Buttons are disabled until input switching is verified; the active "
                      "input is highlighted live.")
        note.setWordWrap(True)
        note.setStyleSheet("border: none;")
        card.body().addWidget(note)
        return card

    def _build_sound_mode_card(self) -> QWidget:
        card = Card("Sound Mode", "purple")
        grid = QGridLayout()
        grid.setSpacing(8)
        self.mode_buttons: list[tuple[str, QPushButton]] = []
        for index, (label, command) in enumerate(SOUND_MODES):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setMinimumHeight(44)
            button.setToolTip(f"Candidate command: {command}")
            button.clicked.connect(lambda _=False, c=command: self.send_command(c))
            self.mode_buttons.append((command, button))
            grid.addWidget(button, index // 3, index % 3)
        card.body().addLayout(grid)
        return card

    def _build_audio_card(self) -> QWidget:
        card = Card("Current Audio", "teal")
        form = QFormLayout()
        self.sample_rate_label = QLabel("—")
        self.sound_mode_value_label = QLabel("—")
        self.geq_state_label = QLabel("—")
        for label in (self.sample_rate_label, self.sound_mode_value_label, self.geq_state_label):
            label.setStyleSheet("font-weight: 700; border: none;")
        form.addRow("Sample rate:", self.sample_rate_label)
        form.addRow("Sound mode:", self.sound_mode_value_label)
        form.addRow("Graphic EQ:", self.geq_state_label)
        card.body().addLayout(form)
        return card

    def _build_status_card(self) -> QWidget:
        card = Card("Receiver Status", "green")
        form = QFormLayout()
        self.power_label = QLabel("Unknown")
        self.main_zone_label = QLabel("Unknown")
        self.zone2_label = QLabel("Unknown")
        self.status_input_label = QLabel("—")
        self.status_volume_label = QLabel("—")
        self.mute_label = QLabel("—")
        self.sync_label = QLabel("No events yet")
        for label in (
            self.power_label,
            self.main_zone_label,
            self.zone2_label,
            self.status_input_label,
            self.status_volume_label,
            self.mute_label,
        ):
            label.setStyleSheet("font-weight: 700; border: none;")
        form.addRow("Power:", self.power_label)
        form.addRow("Main zone:", self.main_zone_label)
        form.addRow("Zone 2:", self.zone2_label)
        form.addRow("Input:", self.status_input_label)
        form.addRow("Volume:", self.status_volume_label)
        form.addRow("Mute:", self.mute_label)
        form.addRow("Last event:", self.sync_label)
        card.body().addLayout(form)
        return card

    def _build_profiles_card(self) -> QWidget:
        card = Card("Profiles", "magenta")
        row = QHBoxLayout()
        self.profiles_combo = QComboBox()
        self.profiles_combo.setMinimumWidth(240)
        row.addWidget(self.profiles_combo)
        self.profile_name_edit = QLineEdit()
        self.profile_name_edit.setPlaceholderText("New profile name")
        row.addWidget(self.profile_name_edit)
        save_button = QPushButton("Save current state")
        save_button.clicked.connect(self.save_profile)
        row.addWidget(save_button)
        apply_button = QPushButton("Apply selected")
        apply_button.clicked.connect(self.apply_selected_profile)
        row.addWidget(apply_button)
        self.auto_apply_box = QCheckBox("Apply last profile after connect")
        self.auto_apply_box.setChecked(bool(self.profile_store.get("auto_apply", True)))
        self.auto_apply_box.toggled.connect(self._auto_apply_toggled)
        row.addWidget(self.auto_apply_box)
        row.addStretch(1)
        self.profile_status_label = QLabel("")
        self.profile_status_label.setStyleSheet("border: none; font-weight: 700;")
        row.addWidget(self.profile_status_label)
        card.body().addLayout(row)
        self._refresh_profiles_combo()
        return card

    def _refresh_profiles_combo(self) -> None:
        self.profiles_combo.clear()
        last = self.profile_store.get("last")
        for name in sorted(self.profile_store.get("profiles", {})):
            self.profiles_combo.addItem(name)
        if last:
            index = self.profiles_combo.findText(last)
            if index >= 0:
                self.profiles_combo.setCurrentIndex(index)

    def _persist_profiles(self) -> None:
        if not self.simulated:
            try:
                profiles.save_store(self.profile_store)
            except OSError as exc:
                self.profile_status.emit(f"Could not save profiles: {exc}")

    def _auto_apply_toggled(self, checked: bool) -> None:
        self.profile_store["auto_apply"] = checked
        self._persist_profiles()

    def save_profile(self) -> None:
        if self.controller is None:
            self.profile_status.emit("Connect first")
            return
        name = self.profile_name_edit.text().strip() or self.profiles_combo.currentText().strip()
        if not name:
            self.profile_status.emit("Enter a profile name")
            return
        snapshot = self.controller.current_snapshot()
        profile = profiles.profile_from_snapshot(name, snapshot)
        self.profile_store.setdefault("profiles", {})[name] = profiles.profile_to_dict(profile)
        self.profile_store["last"] = name
        self._persist_profiles()
        self._refresh_profiles_combo()
        self.profile_name_edit.clear()
        self.profile_status.emit(f"Saved '{name}'")

    def apply_selected_profile(self) -> None:
        name = self.profiles_combo.currentText().strip()
        self._apply_profile_by_name(name)

    def _apply_profile_by_name(self, name: str) -> None:
        data = self.profile_store.get("profiles", {}).get(name)
        if not data:
            self.profile_status.emit("No profile selected")
            return
        if self.controller is None:
            self.profile_status.emit("Connect first")
            return
        profile = profiles.profile_from_dict(name, data)
        commands = profiles.apply_commands(profile, self._limit_value())
        self.profile_store["last"] = name
        self._persist_profiles()
        controller = self.controller

        def run() -> None:
            self.profile_status.emit(f"Applying '{name}'…")
            try:
                for command in commands:
                    controller.send(command)
                    time.sleep(0.15)
            except Exception as exc:
                self.profile_status.emit(f"Apply failed: {exc}")
                return
            controller.request_full_status()
            self.profile_status.emit(f"Applied '{name}' ✓")

        threading.Thread(target=run, daemon=True).start()

    def _maybe_auto_apply(self, snapshot) -> None:
        if not self._auto_apply_pending or not self.auto_apply_box.isChecked():
            return
        if snapshot.volume is None or not snapshot.trims_db:
            return
        last = self.profile_store.get("last")
        if last and last in self.profile_store.get("profiles", {}):
            self._auto_apply_pending = False
            self._apply_profile_by_name(last)
        else:
            self._auto_apply_pending = False

    # ----------------------------------------------------------- behavior
    def _controller_proxy(self):
        window = self

        class _Proxy:
            def send(self, command: str) -> None:
                window.send_command(command)

            def request_full_status(self) -> None:
                if window.controller is not None:
                    window.controller.request_full_status()

            def current_snapshot(self) -> ReceiverSnapshot:
                if window.controller is None:
                    return ReceiverSnapshot()
                return window.controller.current_snapshot()

        return _Proxy()

    def _volume_ceiling_raw(self) -> float:
        return max(20.0, min(75.0, 80.0 + self.settings.volume_ceiling_db))

    def _limit_changed(self, value: int) -> None:
        self.settings = Settings(
            host=self.settings.host,
            http_port=self.settings.http_port,
            poll_interval_seconds=self.settings.poll_interval_seconds,
            request_timeout_seconds=self.settings.request_timeout_seconds,
            auto_connect=self.auto_connect_box.isChecked(),
            volume_ceiling_db=float(value) - 80.0,
        )
        self.volume_slider.setRange(0, value * 2)
        if not self.simulated:
            save_settings(self.settings)

    def scan_receivers(self) -> None:
        if self.simulated:
            return
        self.discovery_label.setText("Scanning…")
        worker = _Worker(discover_receivers)
        self._workers.append(worker)
        worker.signals.finished.connect(self._on_discovery)
        self.pool.start(worker)

    def _select_receiver(self) -> None:
        host = self.receivers_combo.currentData()
        if host:
            self.host_edit.setText(host)

    @Slot(object, object)
    def _on_discovery(self, result: DiscoveryResult | None, error: Exception | None) -> None:
        startup = self._startup_scan
        self._startup_scan = False
        if error is not None:
            self.discovery_label.setText(f"Scan failed: {error}")
        else:
            assert result is not None
            self.receivers_combo.clear()
            self.receivers_combo.addItem("Select a discovered receiver", "")
            for receiver in result.receivers:
                name = receiver.name
                if receiver.model and receiver.model.lower() not in name.lower():
                    name = f"{name} ({receiver.model})"
                self.receivers_combo.addItem(f"{name} — {receiver.host}", receiver.host)
            count = len(result.receivers)
            self.discovery_label.setText(
                f"Found {count} device(s)" if count else "No Denon found; enter IP manually"
            )
            if count == 1 and not self.host_edit.text().strip():
                self.receivers_combo.setCurrentIndex(1)
        if (
            startup
            and self.auto_connect_box.isChecked()
            and self.host_edit.text().strip()
            and self.controller is None
        ):
            self.connect_receiver()

    def connect_receiver(self) -> None:
        if self.controller is not None:
            self.disconnect_receiver()
        try:
            if self.simulated:
                from denon_controller.transport.simulation import SimulatedTelnetController

                self.controller = SimulatedTelnetController(
                    on_line=self.bridge.line.emit,
                    on_state=self.bridge.state.emit,
                    on_connection=self.bridge.connection.emit,
                )
            else:
                host = self.host_edit.text().strip()
                self.controller = TelnetController(
                    host,
                    on_line=self.bridge.line.emit,
                    on_state=self.bridge.state.emit,
                    on_connection=self.bridge.connection.emit,
                )
                self.diagnostics_tab.set_host(host)
                self.settings = Settings(
                    host=host,
                    http_port=self.settings.http_port,
                    poll_interval_seconds=self.settings.poll_interval_seconds,
                    request_timeout_seconds=self.settings.request_timeout_seconds,
                    auto_connect=self.auto_connect_box.isChecked(),
                    volume_ceiling_db=self.settings.volume_ceiling_db,
                )
                save_settings(self.settings)
        except Exception as exc:
            self.connection_label.setText(f"Error: {exc}")
            self.controller = None
            return
        self.connection_label.setText("Connecting…")
        self._auto_apply_pending = True
        worker = _Worker(self.controller.connect)
        self._workers.append(worker)
        worker.signals.finished.connect(self._on_connect_finished)
        self.pool.start(worker)

    @Slot(object, object)
    def _on_connect_finished(self, _result, error: Exception | None) -> None:
        if error is not None:
            self.connection_label.setText(f"Offline: {error}")
            self.controller = None

    def disconnect_receiver(self) -> None:
        if self.controller is not None:
            try:
                self.controller.disconnect()
            except Exception:
                pass
            self.controller = None

    def send_command(self, command: str) -> None:
        if self.controller is None:
            self.connection_label.setText("Not connected")
            return
        try:
            self.controller.send(command)
        except Exception as exc:
            self.connection_label.setText(f"Send failed: {exc}")

    def power_on_zones(self) -> None:
        """Power on the receiver (main zone), then Zone 2 once it has woken."""
        self.send_command("PWON")
        # The receiver needs a moment after waking before it accepts zone commands.
        QTimer.singleShot(1000, lambda: self.send_command("Z2ON"))

    def confirm_standby(self) -> None:
        answer = QMessageBox.question(
            self,
            "Confirm standby",
            "Put the receiver in standby?\nThis switches off the main zone and"
            " Zone 2 and interrupts anything currently playing.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._enter_standby()

    def _enter_standby(self) -> None:
        """Switch off Zone 2 while the unit is awake, then enter system standby."""
        self.send_command("Z2OFF")
        self.send_command("PWSTANDBY")

    def toggle_mute(self) -> None:
        self.send_command("MUON" if self.mute_button.isChecked() else "MUOFF")

    def step_volume(self, delta: float) -> None:
        snapshot = (
            self.controller.current_snapshot() if self.controller is not None else None
        )
        current = snapshot.volume if snapshot and snapshot.volume is not None else None
        if current is None:
            return
        target = max(0.0, min(self._limit_value(), current + delta))
        self.send_command(format_volume_command(target))

    def _limit_value(self) -> float:
        return float(self.limit_spin.value())

    def _slider_volume(self) -> None:
        self.send_command(format_volume_command(self.volume_slider.value() / 2))

    # ------------------------------------------------------------- events
    @Slot(str)
    def _on_line(self, line: str) -> None:
        self.diagnostics_tab.append_line(line)

    @Slot(bool, str)
    def _on_connection(self, connected: bool, detail: str) -> None:
        self.connection_label.setText(detail)
        color = "#007A3D" if connected else "#C21807"
        self.connection_label.setStyleSheet(
            f"font-weight: 800; border: none; color: {color};"
        )

    @Slot(object)
    def _on_state(self, snapshot: ReceiverSnapshot) -> None:
        if snapshot.power_on is not None:
            self.power_label.setText("On" if snapshot.power_on else "Standby")
        if snapshot.main_zone_on is not None:
            self.main_zone_label.setText("On" if snapshot.main_zone_on else "Off")
        if snapshot.zone2_on is not None:
            self.zone2_label.setText("On" if snapshot.zone2_on else "Off")
        if snapshot.input_source:
            self.input_label.setText(snapshot.input_source)
            self.status_input_label.setText(snapshot.input_source)
            for key, button in self.source_buttons.items():
                button.setChecked(key == snapshot.input_source)
        if snapshot.sound_mode:
            self.mode_label.setText(f"Mode: {snapshot.sound_mode}")
            self.sound_mode_value_label.setText(snapshot.sound_mode)
            reported = snapshot.sound_mode.replace(" ", "").upper()
            for command, button in self.mode_buttons:
                expected = command[2:].replace(" ", "").upper()
                button.setChecked(
                    expected in reported or reported in expected if reported else False
                )
        if snapshot.volume is not None:
            db = snapshot.volume - 80.0
            self.volume_value_label.setText(f"{snapshot.volume:.1f}")
            self.volume_value_label.setToolTip(f"{db:+.1f} dB")
            self.status_volume_label.setText(f"{snapshot.volume:.1f} ({db:+.1f} dB)")
            if not self.volume_slider.isSliderDown():
                self.volume_slider.setValue(int(snapshot.volume * 2))
        if snapshot.muted is not None:
            self.mute_label.setText("Muted" if snapshot.muted else "Off")
            self.mute_button.setChecked(snapshot.muted)
        if snapshot.sample_rate:
            self.sample_rate_label.setText(snapshot.sample_rate)
        if snapshot.geq_on is not None:
            self.geq_state_label.setText("On" if snapshot.geq_on else "Off")
        if snapshot.updated_at is not None:
            self.sync_label.setText(snapshot.updated_at.strftime("%H:%M:%S"))
        self.equalizer_tab.apply_snapshot(snapshot)
        self._maybe_auto_apply(snapshot)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self.speaker_engine.active:
            self.speaker_engine.end_session()
        self.disconnect_receiver()
        super().closeEvent(event)
