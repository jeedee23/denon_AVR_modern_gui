from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from denon_controller.models import DeviceState
from denon_controller.services.capability_registry import capabilities
from denon_controller.services.diagnostics import Event
from denon_controller.ui.overview import button


class DiagnosticsPage(QWidget):
    refresh = Signal()
    export = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.summary = QLabel("Not connected")
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.probe = button(
            "Read-only status probe", "Only fixed status endpoints / query commands."
        )
        self.probe.clicked.connect(self.refresh)
        layout.addWidget(self.probe)
        export = button(
            "Export sanitized diagnostic session…", "Writes only after you select a file."
        )
        export.clicked.connect(self.export)
        layout.addWidget(export)
        note = QLabel(
            "Bounded in-memory event log (last 200 events). No packet interception, "
            "automatic disk logs or raw command terminal. Review exports before sharing."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.capabilities = QPlainTextEdit()
        self.capabilities.setReadOnly(True)
        self.capabilities.setAccessibleName("Capability evidence")
        layout.addWidget(self.capabilities)
        self.events = QPlainTextEdit()
        self.events.setReadOnly(True)
        self.events.setAccessibleName("Sanitized event log")
        layout.addWidget(self.events)

    def update_state(self, state: DeviceState, events: list[Event]) -> None:
        timing = (
            f"{state.roundtrip_ms:.0f} ms" if state.roundtrip_ms is not None else "Not available"
        )
        self.summary.setText(
            f"Protocol: {state.protocol} | Roundtrip: {timing}\n"
            f"Firmware: Not available | Last error: {state.last_error or 'None'}"
        )
        self.capabilities.setPlainText(
            "\n".join(f"{cap.name}: {cap.evidence}\n  {cap.detail}" for cap in capabilities(state))
        )
        self.events.setPlainText(
            "\n".join(f"{event.timestamp} [{event.category}] {event.result}" for event in events)
        )
