from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from denon_controller.ui.overview import button


class Channels(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        for text in (
            "Input/output speaker layout: Not available",
            "Temporary per-channel trims: Unverified — no reliable readback established",
            "Saved calibration, speaker distances, crossovers and EQ: out of scope (no writes)",
        ):
            label = QLabel(text)
            label.setWordWrap(True)
            layout.addWidget(label)
        control = button("Temporary trims — Unverified", "No CV or calibration commands are sent.")
        control.setEnabled(False)
        layout.addWidget(control)
        layout.addStretch()
