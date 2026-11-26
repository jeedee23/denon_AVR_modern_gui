from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QLabel, QVBoxLayout, QWidget

from denon_controller.models import DeviceState
from denon_controller.ui.overview import button


class Sources(QWidget):
    action = Signal(str, object)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        label = QLabel(
            "Inputs reported by this receiver only. Renamed labels are shown where available.\n"
            "Input writes remain UNVERIFIED, even when the input list can be read."
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        self.inputs = QComboBox()
        self.inputs.setAccessibleName("Reported inputs")
        layout.addWidget(self.inputs)
        self.select = button(
            "Select input", "Send only the selected receiver-reported source token."
        )
        self.select.clicked.connect(lambda: self.action.emit("source", self.inputs.currentData()))
        layout.addWidget(self.select)
        self.status = QLabel("Not available — receiver has not reported an input list.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addStretch()

    def update_state(self, state: DeviceState, enabled: bool) -> None:
        previous = self.inputs.currentData()
        self.inputs.clear()
        for token, label in state.sources.items():
            self.inputs.addItem(label, token)
        index = self.inputs.findData(previous or state.main.source)
        if index >= 0:
            self.inputs.setCurrentIndex(index)
        self.select.setEnabled(enabled and bool(state.sources))
        self.status.setText(
            f"{len(state.sources)} reported inputs."
            if state.sources
            else "Not available — no recognized input list. No universal source list is assumed."
        )
