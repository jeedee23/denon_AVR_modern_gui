"""Equalizer tab: realtime graphic EQ sliders and channel trim controls."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from denon_controller.transport.telnet import (
    EQ_BANDS,
    EQ_GROUPS,
    TRIM_CHANNELS,
    ReceiverSnapshot,
    db_to_eq_level,
    db_to_level,
)

EQ_MIN_DB = -20.0
EQ_MAX_DB = 6.0
TRIM_MIN_DB = -12.0
TRIM_MAX_DB = 12.0

# EQ speaker group -> channel-trim codes the receiver reports only when those
# speakers are fitted. Groups without any fitted speaker accept EQ writes but
# have no audible effect, so the UI flags and disables them.
EQ_GROUP_TRIMS = {
    "FRO": ("FL", "FR"),
    "CEN": ("C",),
    "SUR": ("SL", "SR"),
    "SBK": ("SBL", "SBR"),
    "FRH": ("FHL", "FHR"),
    "TFR": ("TFL", "TFR"),
    "TPM": ("TML", "TMR"),
    "FRD": ("FDL", "FDR"),
    "SUD": ("SDL", "SDR"),
}


def _slider_to_db(value: int) -> float:
    return value / 2


def _db_to_slider(db: float) -> int:
    return int(round(db * 2))


# Combo entry that applies the same band values to every fitted group.
ALL_GROUPS = "ALL"

# Room-oriented display names for this installation; receiver terms in EQ_GROUPS
# are used as fallback for any other fitted group.
GROUP_LABELS = {
    "FRO": "Front",
    "CEN": "Center",
    "SUR": "Surround front",  # surround pair hung at front level, 2.5 m high
    "SUD": "Surround back",  # Dolby surround pair ~6 m back
}


class EqualizerTab(QWidget):
    def __init__(self, send_command, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.send_command = send_command
        self._updating = False
        self._eq_values: dict[str, list[float]] = {}
        self._trims: dict[str, float] = {}
        self._isolate_baseline: dict[str, float] | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        top = QHBoxLayout()
        self.geq_button = QPushButton("Graphic EQ: unknown")
        self.geq_button.setCheckable(True)
        self.geq_button.setMinimumHeight(48)
        self.geq_button.clicked.connect(self.toggle_geq)
        self.group_combo = QComboBox()
        for code, label in EQ_GROUPS.items():
            self.group_combo.addItem(GROUP_LABELS.get(code, label), code)
        self.group_combo.currentIndexChanged.connect(self._on_group_changed)
        self.isolate_button = QPushButton("Isolate")
        self.isolate_button.setCheckable(True)
        self.isolate_button.setMinimumHeight(48)
        self.isolate_button.setToolTip(
            "Dims every other speaker (including the subwoofer) to −12 dB — the "
            "receiver's minimum trim, not a full mute — so you hear this group "
            "alone while tuning. Toggle off to restore the previous trims."
        )
        self.isolate_button.clicked.connect(self.toggle_isolate)
        top.addWidget(self.geq_button)
        top.addWidget(QLabel("Speaker group:"))
        top.addWidget(self.group_combo)
        top.addWidget(self.isolate_button)
        top.addStretch(1)
        self.lag_label = QLabel("Note: the receiver applies EQ changes with a noticeable lag.")
        top.addWidget(self.lag_label)
        layout.addLayout(top)

        sliders = QGridLayout()
        sliders.setHorizontalSpacing(18)
        self.band_sliders: list[QSlider] = []
        self.band_values: list[QLabel] = []
        for column, band in enumerate(EQ_BANDS):
            value_label = QLabel("—")
            value_label.setAlignment(Qt.AlignHCenter)
            value_label.setStyleSheet("font-weight: 700; border: none;")
            slider = QSlider(Qt.Vertical)
            slider.setRange(_db_to_slider(EQ_MIN_DB), _db_to_slider(EQ_MAX_DB))
            slider.setMinimumHeight(260)
            slider.setTickInterval(4)
            slider.setTickPosition(QSlider.TicksBothSides)
            slider.valueChanged.connect(
                lambda value, label=value_label: label.setText(f"{_slider_to_db(value):+.1f}")
            )
            slider.sliderReleased.connect(self.send_band_values)
            band_label = QLabel(band)
            band_label.setAlignment(Qt.AlignHCenter)
            band_label.setStyleSheet("border: none;")
            sliders.addWidget(value_label, 0, column)
            sliders.addWidget(slider, 1, column, alignment=Qt.AlignHCenter)
            sliders.addWidget(band_label, 2, column)
            self.band_sliders.append(slider)
            self.band_values.append(value_label)
        layout.addLayout(sliders)

        trims_title = QLabel("Channel trims (temporary levels, −12…+12 dB)")
        trims_title.setObjectName("CardTitle")
        trims_title.setStyleSheet("border: none;")
        layout.addWidget(trims_title)

        trim_grid = QGridLayout()
        trim_grid.setHorizontalSpacing(14)
        self.trim_sliders: dict[str, QSlider] = {}
        self.trim_values: dict[str, QLabel] = {}
        for row, (code, label) in enumerate(TRIM_CHANNELS.items()):
            name = QLabel(label)
            name.setStyleSheet("border: none;")
            slider = QSlider(Qt.Horizontal)
            slider.setRange(_db_to_slider(TRIM_MIN_DB), _db_to_slider(TRIM_MAX_DB))
            value_label = QLabel("—")
            value_label.setMinimumWidth(64)
            value_label.setStyleSheet("font-weight: 700; border: none;")
            slider.valueChanged.connect(
                lambda value, lab=value_label: lab.setText(f"{_slider_to_db(value):+.1f} dB")
            )
            slider.sliderReleased.connect(
                lambda code=code, s=slider: self.send_trim(code, _slider_to_db(s.value()))
            )
            trim_grid.addWidget(name, row, 0)
            trim_grid.addWidget(slider, row, 1)
            trim_grid.addWidget(value_label, row, 2)
            self.trim_sliders[code] = slider
            self.trim_values[code] = value_label
        layout.addLayout(trim_grid)
        layout.addStretch(1)

    def toggle_geq(self) -> None:
        command = "PSGEQ ON" if self.geq_button.isChecked() else "PSGEQ OFF"
        self.send_command(command)

    def send_band_values(self) -> None:
        if self._updating:
            return
        group = self.group_combo.currentData()
        values = [_slider_to_db(slider.value()) for slider in self.band_sliders]
        encoded = ":".join(db_to_eq_level(db) for db in values)
        targets = self._fitted_groups() if group == ALL_GROUPS else [group]
        for code in targets:
            self.send_command(f"SSAEQLRS{code} {encoded}")

    def send_trim(self, code: str, db: float) -> None:
        if self._updating:
            return
        self.send_command(f"CV{code} {db_to_level(db)}")

    def refresh_sliders(self) -> None:
        group = self.group_combo.currentData()
        if group == ALL_GROUPS:
            # Representative values: first fitted group with known bands.
            values = next(
                (self._eq_values[g] for g in self._fitted_groups() if g in self._eq_values),
                None,
            )
        else:
            values = self._eq_values.get(group)
        if values is None:
            return
        self._updating = True
        try:
            for slider, db in zip(self.band_sliders, values, strict=False):
                if not slider.isSliderDown():
                    slider.setValue(_db_to_slider(db))
        finally:
            self._updating = False

    def apply_snapshot(self, snapshot: ReceiverSnapshot) -> None:
        self._updating = True
        try:
            if snapshot.geq_on is not None:
                self.geq_button.setChecked(snapshot.geq_on)
                self.geq_button.setText(
                    "Graphic EQ: ON" if snapshot.geq_on else "Graphic EQ: OFF"
                )
            self._eq_values = snapshot.eq_bands_db
            self._trims = dict(snapshot.trims_db)
            for code, db in snapshot.trims_db.items():
                slider = self.trim_sliders.get(code)
                if slider is not None and not slider.isSliderDown():
                    slider.setValue(_db_to_slider(db))
        finally:
            self._updating = False
        self._update_group_choices()
        self.refresh_sliders()

    def _fitted_groups(self) -> list[str]:
        """EQ groups whose speakers exist, per the trim readback (CV?)."""
        return [
            code
            for code in EQ_GROUPS
            if any(trim in self._trims for trim in EQ_GROUP_TRIMS.get(code, ()))
        ]

    def _update_group_choices(self) -> None:
        """Offer only real speaker groups for this layout, plus 'All'."""
        if not self._trims:
            return
        desired = self._fitted_groups() + [ALL_GROUPS]
        current = [self.group_combo.itemData(i) for i in range(self.group_combo.count())]
        if current == desired:
            return
        selected = self.group_combo.currentData()
        self.group_combo.blockSignals(True)
        try:
            self.group_combo.clear()
            for code in desired[:-1]:
                self.group_combo.addItem(GROUP_LABELS.get(code, EQ_GROUPS[code]), code)
            self.group_combo.addItem("All", ALL_GROUPS)
            index = self.group_combo.findData(selected)
            self.group_combo.setCurrentIndex(index if index >= 0 else 0)
        finally:
            self.group_combo.blockSignals(False)
        self._on_group_changed()

    # ---------------------------------------------------------- isolation
    def _on_group_changed(self) -> None:
        group = self.group_combo.currentData()
        self.isolate_button.setEnabled(group != ALL_GROUPS)
        if group == ALL_GROUPS and self.isolate_button.isChecked():
            self.isolate_button.setChecked(False)
            self._release_isolation()
        elif self.isolate_button.isChecked():
            self._apply_isolation()
        self.refresh_sliders()

    def toggle_isolate(self) -> None:
        if self.isolate_button.isChecked():
            self._apply_isolation()
        else:
            self._release_isolation()

    def _apply_isolation(self) -> None:
        """Dim every channel outside the selected group to the trim minimum."""
        group = self.group_combo.currentData()
        if group in (None, ALL_GROUPS) or not self._trims:
            self.isolate_button.setChecked(False)
            return
        if self._isolate_baseline is None:
            self._isolate_baseline = dict(self._trims)
        keep = set(EQ_GROUP_TRIMS.get(group, ()))
        for code, baseline_db in self._isolate_baseline.items():
            target = baseline_db if code in keep else TRIM_MIN_DB
            self.send_command(f"CV{code} {db_to_level(target)}")

    def _release_isolation(self) -> None:
        if self._isolate_baseline is None:
            return
        for code, db in self._isolate_baseline.items():
            self.send_command(f"CV{code} {db_to_level(db)}")
        self._isolate_baseline = None
