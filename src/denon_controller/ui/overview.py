from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from denon_controller.models import Connection, DeviceState


def power_text(value: bool | None) -> str:
    return "Not available" if value is None else ("On" if value else "Standby")


def button(text: str, tooltip: str) -> QPushButton:
    widget = QPushButton(text)
    widget.setMinimumHeight(40)
    widget.setToolTip(tooltip)
    return widget


class Overview(QWidget):
    action = Signal(str, object)
    candidate_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        heading = QLabel("Main Zone")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)
        form = QFormLayout()
        self.system = QLabel("Not available")
        self.main_power = QLabel("Not available")
        self.source = QLabel("Not available")
        self.mode = QLabel("Not available")
        self.volume = QLabel("Not available")
        self.mute = QLabel("Not available")
        for label, widget in (
            ("System power (PW)", self.system),
            ("Main power (ZM)", self.main_power),
            ("Input", self.source),
            ("Listening mode", self.mode),
            ("Measured volume", self.volume),
            ("Mute", self.mute),
        ):
            widget.setTextFormat(Qt.TextFormat.PlainText)
            form.addRow(label, widget)
        layout.addLayout(form)
        power_row = QHBoxLayout()
        self.power_on = button(
            "Power ON", "Owner-verified HTTP command. Readback is still required."
        )
        self.standby = button(
            "System standby…", "Unverified candidate; affects the whole receiver."
        )
        power_row.addWidget(self.power_on)
        power_row.addWidget(self.standby)
        layout.addLayout(power_row)
        self.power_on.clicked.connect(lambda: self.action.emit("power_on", None))
        volume_row = QHBoxLayout()
        self.down = button("− 0.5 dB", "Reduce volume using a bounded absolute half-step.")
        self.up = button("+ 0.5 dB", "Increase volume only below your configured ceiling.")
        self.mute_on = button("Mute", "Set mute ON; never a blind toggle.")
        self.mute_off = button("Unmute", "Unverified candidate. Check measured volume first.")
        for widget in (self.down, self.up, self.mute_on, self.mute_off):
            volume_row.addWidget(widget)
        layout.addLayout(volume_row)
        self.down.clicked.connect(lambda: self.action.emit("volume_down", None))
        self.up.clicked.connect(lambda: self.action.emit("volume_up", None))
        self.mute_on.clicked.connect(lambda: self.action.emit("mute", True))
        self.mute_off.clicked.connect(lambda: self.action.emit("mute", False))
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setAccessibleName("Main Zone absolute volume")
        self.slider.setToolTip("Candidate absolute volume. Drag and release to send once.")
        self.slider.setRange(-160, -60)
        self.slider.setEnabled(False)
        # State changes and keyboard focus never send a volume write.
        self.slider.sliderReleased.connect(
            lambda: self.action.emit("volume", self.slider.value() / 2)
        )
        layout.addWidget(self.slider)
        self.ceiling_label = QLabel()
        layout.addWidget(self.ceiling_label)
        self.candidates = QCheckBox("Enable UNVERIFIED basic controls for this session…")
        self.candidates.setToolTip(
            "Readback is not proof of write support. "
            "Enable only for deliberate, supervised testing."
        )
        self.candidates.toggled.connect(self.candidate_changed)
        layout.addWidget(self.candidates)
        self.outcome = QLabel("No commands sent")
        self.outcome.setWordWrap(True)
        self.outcome.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.outcome)
        unavailable = QLabel(
            "Audio format · output channels · sample rate · artist/track: Not available"
        )
        unavailable.setWordWrap(True)
        layout.addWidget(unavailable)
        layout.addStretch()

    def update_state(
        self,
        state: DeviceState,
        *,
        candidates: bool,
        connected: bool,
        ceiling: float,
        max_age: float = 10,
    ) -> None:
        self.system.setText(power_text(state.system_power))
        self.main_power.setText(power_text(state.main.power))
        self.source.setText(state.main.source or "Not available")
        self.mode.setText(state.surround or "Not available")
        db = state.main.volume_db
        self.volume.setText(f"{db:+.1f} dB" if db is not None else "Not available")
        self.mute.setText(
            "Not available" if state.main.mute is None else ("Muted" if state.main.mute else "Off")
        )
        usable = connected and state.connection == Connection.CONNECTED and candidates
        volume_fresh = db is not None and state.is_fresh("main.volume_db", max_age)
        mute_fresh = state.main.mute is not None and state.is_fresh("main.mute", max_age)
        self.power_on.setEnabled(connected)
        self.standby.setEnabled(usable and state.is_fresh("system_power", max_age))
        self.up.setEnabled(usable and volume_fresh and db < ceiling)
        self.down.setEnabled(usable and volume_fresh and db > -80)
        self.mute_on.setEnabled(usable and mute_fresh)
        self.mute_off.setEnabled(usable and mute_fresh and volume_fresh and db <= ceiling)
        self.slider.setEnabled(usable and volume_fresh)
        if not self.slider.isSliderDown():
            self.slider.setMaximum(int(ceiling * 2))
            if db is not None:
                self.slider.blockSignals(True)
                self.slider.setValue(int(min(db, ceiling) * 2))
                self.slider.blockSignals(False)
        self.ceiling_label.setText(
            f"Absolute-setting ceiling: {ceiling:+.1f} dB. "
            "Above ceiling, use − to reduce volume. Slider sends on mouse release only."
        )
        self.outcome.setText(
            state.outcome + (f"\nError: {state.last_error}" if state.last_error else "")
        )
