"""Diagnostics tab: live Telnet event log with noise filter and export."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from denon_controller.transport.telnet import NOISE_PREFIXES

MAX_LINES = 3000


class DiagnosticsTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._host = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        controls = QHBoxLayout()
        self.hide_noise = QCheckBox("Hide periodic status noise (SSSPC/OPSTS/…)")
        self.hide_noise.setChecked(True)
        clear_button = QPushButton("Clear")
        clear_button.clicked.connect(lambda: self.log.setPlainText(""))
        export_button = QPushButton("Export sanitized log…")
        export_button.clicked.connect(self.export_log)
        controls.addWidget(self.hide_noise)
        controls.addStretch(1)
        controls.addWidget(clear_button)
        controls.addWidget(export_button)
        layout.addLayout(controls)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(MAX_LINES)
        layout.addWidget(self.log, stretch=1)
        hint = QLabel("'>' sent to receiver, '<' received. Exports mask the receiver address.")
        layout.addWidget(hint)

    def set_host(self, host: str) -> None:
        self._host = host

    def append_line(self, line: str) -> None:
        payload = line[2:] if len(line) > 2 else line
        if self.hide_noise.isChecked() and payload.startswith(NOISE_PREFIXES):
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log.appendPlainText(f"{timestamp} {line}")

    def export_log(self) -> None:
        target, _ = QFileDialog.getSaveFileName(
            self, "Export sanitized log", "denon-telnet-log.txt", "Text files (*.txt)"
        )
        if not target:
            return
        content = self.log.toPlainText()
        if self._host:
            content = content.replace(self._host, "RECEIVER")
        Path(target).write_text(content, encoding="utf-8")
