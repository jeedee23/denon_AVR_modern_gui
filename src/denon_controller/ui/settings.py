from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from denon_controller.settings import Settings, config_path
from denon_controller.ui.overview import button


class SettingsPage(QWidget):
    save_requested = Signal(object)
    discovery_requested = Signal(object)
    error = Signal(str)

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.host = QLineEdit(settings.host)
        self.host.setToolTip("Receiver hostname or private LAN IP. No URL or cloud endpoint.")
        form.addRow("&Receiver hostname / IP", self.host)
        self.http_port = QSpinBox()
        self.telnet_port = QSpinBox()
        for label, widget, value in (
            ("HTTP port", self.http_port, settings.http_port),
            ("TCP / Telnet port", self.telnet_port, settings.telnet_port),
        ):
            widget.setRange(1, 65535)
            widget.setValue(value)
            form.addRow(label, widget)
        self.poll = QDoubleSpinBox()
        self.poll.setRange(2, 120)
        self.poll.setSuffix(" s")
        self.poll.setValue(settings.poll_interval)
        form.addRow("Poll interval", self.poll)
        self.timeout = QDoubleSpinBox()
        self.timeout.setRange(0.2, 5)
        self.timeout.setSuffix(" s / request")
        self.timeout.setValue(settings.timeout)
        form.addRow("Network timeout", self.timeout)
        self.ceiling = QDoubleSpinBox()
        self.ceiling.setRange(-80, 0)
        self.ceiling.setSingleStep(0.5)
        self.ceiling.setSuffix(" dB")
        self.ceiling.setValue(settings.volume_ceiling)
        form.addRow("Safe volume ceiling", self.ceiling)
        self.auto = QCheckBox("Auto-connect (read-only queries on startup)")
        self.auto.setChecked(settings.auto_connect)
        form.addRow(self.auto)
        self.verbose = QCheckBox("Include parsed numeric status in in-memory diagnostics")
        self.verbose.setChecked(settings.diagnostics_verbose)
        form.addRow(self.verbose)
        self.discovery = QCheckBox("Allow explicit local UDP discovery")
        self.discovery.setChecked(settings.discovery_enabled)
        form.addRow(self.discovery)
        self.theme = QComboBox()
        self.theme.addItems(["system", "light", "dark"])
        self.theme.setCurrentText(settings.theme)
        form.addRow("Theme", self.theme)
        layout.addLayout(form)
        self.save = button(
            "Save settings", "Disconnect first. Stored only in your user config directory."
        )
        self.save.clicked.connect(self._save)
        layout.addWidget(self.save)
        self.discover = button(
            "Discover local renderers…", "One explicit SSDP search; no port scanning."
        )
        self.discover.clicked.connect(self._discover)
        layout.addWidget(self.discover)
        note = QLabel(f"Configuration: {config_path()}\nDisconnect before saving or discovering.")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()

    def values(self) -> Settings:
        return Settings(
            host=self.host.text().strip(),
            http_port=self.http_port.value(),
            telnet_port=self.telnet_port.value(),
            poll_interval=self.poll.value(),
            timeout=self.timeout.value(),
            volume_ceiling=self.ceiling.value(),
            auto_connect=self.auto.isChecked(),
            diagnostics_verbose=self.verbose.isChecked(),
            discovery_enabled=self.discovery.isChecked(),
            theme=self.theme.currentText(),
        )

    def _save(self) -> None:
        try:
            settings = self.values()
            settings.save()
        except (OSError, ValueError) as exc:
            self.error.emit(str(exc))
            return
        self.save_requested.emit(settings)

    def _discover(self) -> None:
        if not self.discovery.isChecked():
            self.error.emit("Enable explicit local UDP discovery first.")
            return
        try:
            self.discovery_requested.emit(self.values())
        except ValueError as exc:
            self.error.emit(str(exc))
