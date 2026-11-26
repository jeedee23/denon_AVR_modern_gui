from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from denon_controller.models import DeviceState
from denon_controller.ui.overview import power_text


class Zones(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        note = QLabel(
            "Zone 2 is monitored separately where readback exists. Zone 2 writes are disabled "
            "until independently validated. System PW is never treated as Main Zone ZM."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()

    def update_state(self, state: DeviceState) -> None:
        zone = state.zone2
        volume = f"{zone.volume_db:+.1f} dB" if zone.volume_db is not None else "Not available"
        mute = "Not available" if zone.mute is None else ("Muted" if zone.mute else "Off")
        self.status.setText(
            f"Main Zone: {power_text(state.main.power)}\n\n"
            f"Zone 2 power: {power_text(zone.power)}\n"
            f"Zone 2 volume: {volume}\nZone 2 mute: {mute}\n"
            f"Zone 2 source: {zone.source or 'Not available'}"
        )
