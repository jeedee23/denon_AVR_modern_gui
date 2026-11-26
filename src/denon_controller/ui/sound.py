from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QLabel, QVBoxLayout, QWidget

from denon_controller.models import DeviceState
from denon_controller.ui.overview import button


class Sound(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.current = QLabel("Not available")
        self.current.setTextFormat(Qt.TextFormat.PlainText)
        form = QFormLayout()
        form.addRow("Reported listening mode", self.current)
        layout.addLayout(form)
        for name in (
            "Listening mode selection",
            "Audyssey MultEQ XT32",
            "Dynamic EQ / reference offset",
            "Dynamic Volume",
            "Tone / bass / treble / dialogue",
        ):
            control = button(
                name + " — Unverified", "No validated command and readback on this AVR."
            )
            control.setEnabled(False)
            layout.addWidget(control)
        note = QLabel(
            "Read-only until separately validated on this firmware. Availability may depend "
            "on the current input signal and listening mode; no universal mode list is assumed."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()

    def update_state(self, state: DeviceState) -> None:
        self.current.setText(state.surround or "Not available")
