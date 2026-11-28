"""Speaker test tab: per-speaker tones with capture, restore, and verification."""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from denon_controller import audio
from denon_controller.transport.telnet import (
    TRIM_CHANNELS,
    db_to_level,
    format_volume_command,
)

TEST_VOLUME = 50.0  # receiver 0-98 scale, requested by the owner
TONE_DBFS = -20.0


class SpeakerTestEngine(QObject):
    """Owns the capture -> test -> restore lifecycle off the GUI thread."""

    status = Signal(str)
    session_changed = Signal(bool)
    restore_result = Signal(bool, str)

    def __init__(self, controller) -> None:
        super().__init__()
        self.controller = controller
        self.active = False
        self.playing_step: int | None = None
        self._generation = 0
        self._audio_lock = threading.Lock()  # serializes playback loops; prevents native races
        self.baseline_volume: float | None = None
        self.baseline_trims: dict[str, float] = {}
        self.baseline_mode: str | None = None
        self._player: audio.TonePlayer | None = None
        self._lock = threading.Lock()

    def start_session(self) -> None:
        threading.Thread(target=self._start_session, daemon=True).start()

    def _start_session(self) -> None:
        with self._lock:
            if self.active:
                return
            snapshot = self.controller.current_snapshot()
            missing = [c for c in TRIM_CHANNELS if c not in snapshot.trims_db]
            if snapshot.volume is None or missing:
                self.controller.request_full_status()
                time.sleep(2.5)
                snapshot = self.controller.current_snapshot()
                missing = [c for c in TRIM_CHANNELS if c not in snapshot.trims_db]
            if snapshot.volume is None or missing:
                self.status.emit(f"Cannot capture baseline (missing: {missing or 'volume'})")
                return
            self.baseline_volume = snapshot.volume
            self.baseline_trims = dict(snapshot.trims_db)
            self.baseline_mode = snapshot.sound_mode
            try:
                self.controller.send(format_volume_command(TEST_VOLUME))
                # Stream Direct plays the multichannel input as-is ("Multi Ch In");
                # Multi Ch Stereo would upmix tones into the Dolby surround pair.
                if self.baseline_mode is not None:
                    self.controller.send("MSDIRECT")
                    time.sleep(0.12)
                for code in TRIM_CHANNELS:
                    self.controller.send(f"CV{code} {db_to_level(0.0)}")
                    time.sleep(0.12)
            except Exception as exc:
                self.status.emit(f"Setup failed: {exc}")
                self._restore_locked()
                return
            self.active = True
        self.session_changed.emit(True)
        self.status.emit(
            f"Test session active: volume {TEST_VOLUME:.0f}, trims 0 dB, Stream Direct mode "
            f"(baseline captured: volume {self.baseline_volume:.1f}, "
            f"mode {self.baseline_mode or 'unknown'})"
        )

    def play_step(self, step_index: int) -> None:
        if not self.active:
            self.status.emit("Start the test session first")
            return
        self._generation += 1
        generation = self._generation
        self.stop_audio(bump=False)
        threading.Thread(
            target=self._play_loop, args=(step_index, generation), daemon=True
        ).start()

    def _play_loop(self, step_index: int, generation: int) -> None:
        label, channel, _ = audio.SPEAKER_STEPS[step_index]
        with self._audio_lock:  # wait until any previous loop has fully exited
            if self._generation != generation:
                return
            try:
                device, channels = audio.find_output_device()
                player = audio.TonePlayer(device, channels)
                self._player = player
                if channels < audio.CHANNEL_COUNT:
                    self.status.emit(
                        f"Warning: HDMI device reports only {channels} channels — "
                        "set '1 - DENON-AVR' to 7.1 Surround in Windows Sound settings "
                        "for full per-speaker testing."
                    )
                cycle = (
                    audio.build_sweep(TONE_DBFS)
                    if label.startswith("Subwoofer")
                    else audio.build_pattern(TONE_DBFS)
                )
                self.playing_step = step_index
                self.status.emit(
                    f"Playing (looping): {label} — Next/Previous switches, STOP ends"
                )
                player.play_loop(
                    cycle, channel, should_continue=lambda: self._generation == generation
                )
            except Exception as exc:
                self.status.emit(f"Playback failed: {exc}")
            finally:
                if self._generation == generation:
                    self.playing_step = None
                    self.status.emit(f"Stopped: {label}")

    def stop_audio(self, bump: bool = True) -> None:
        if bump:
            self._generation += 1
            self.playing_step = None
        if self._player is not None:
            self._player.stop()

    def end_session(self) -> None:
        threading.Thread(target=self._end_session, daemon=True).start()

    def _end_session(self) -> None:
        self.stop_audio()
        with self._lock:
            if not self.active and self.baseline_volume is None:
                return
            self._restore_locked()
            self.active = False
        self.session_changed.emit(False)

    def _restore_locked(self) -> None:
        if self.baseline_volume is None:
            return
        self.status.emit("Restoring receiver state…")
        try:
            self.controller.send(format_volume_command(self.baseline_volume))
            if self.baseline_mode is not None:
                self.controller.send(f"MS{self.baseline_mode}")
                time.sleep(0.12)
            for code, db in self.baseline_trims.items():
                self.controller.send(f"CV{code} {db_to_level(db)}")
                time.sleep(0.12)
        except Exception as exc:
            self.restore_result.emit(False, f"RESTORE FAILED: {exc} — baseline was "
                                     f"volume {self.baseline_volume}, trims {self.baseline_trims},"
                                     f" mode {self.baseline_mode}")
            return
        time.sleep(0.8)
        self.controller.request_full_status()
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline:
            snapshot = self.controller.current_snapshot()
            if (
                snapshot.volume == self.baseline_volume
                and all(
                    abs(snapshot.trims_db.get(code, 99) - db) < 0.01
                    for code, db in self.baseline_trims.items()
                )
                and self._mode_restored(snapshot.sound_mode)
            ):
                self.restore_result.emit(True, "Restored and verified by readback ✓")
                self.baseline_volume = None
                self.baseline_trims = {}
                self.baseline_mode = None
                return
            time.sleep(0.3)
        self.restore_result.emit(False, "Restore sent but readback did not confirm — check values")

    def _mode_restored(self, reported: str | None) -> bool:
        """Tolerant comparison: the receiver echoes mode names with varying spacing."""
        if self.baseline_mode is None:
            return True
        if reported is None:
            return False
        expected = self.baseline_mode.replace(" ", "").upper()
        actual = reported.replace(" ", "").upper()
        return expected in actual or actual in expected


class SpeakerTestTab(QWidget):
    def __init__(self, engine: SpeakerTestEngine) -> None:
        super().__init__()
        self.engine = engine
        self.step = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        info = QLabel(
            "Plays an intermittent identification pattern (430 / 800 / 1000 / 200 Hz) on the "
            "selected speaker, looping until you press Next, Previous, or STOP. The subwoofer "
            "plays a repeating 100→50 Hz sweep. Starting a session sets the receiver to "
            "volume 50 with 0 dB trims and Stream Direct mode (Multi Ch In), so tones stay "
            "on the selected speaker instead of being upmixed to the Dolby surround pair; "
            "ending it restores and verifies your settings. "
            "Note: this receiver has no surround-back speakers — the Back L/R probes fold "
            "into the fronts, and the Surround Dolby pair (mounted behind the surrounds) "
            "cannot be driven over HDMI PCM."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        selector = QHBoxLayout()
        self.prev_button = QPushButton("◀ Previous")
        self.prev_button.setMinimumHeight(56)
        self.prev_button.clicked.connect(lambda: self.move_step(-1))
        self.speaker_label = QLabel()
        self.speaker_label.setObjectName("BigValue")
        self.speaker_label.setStyleSheet("border: none;")
        self.next_button = QPushButton("Next ▶")
        self.next_button.setMinimumHeight(56)
        self.next_button.clicked.connect(lambda: self.move_step(1))
        selector.addWidget(self.prev_button)
        selector.addStretch(1)
        selector.addWidget(self.speaker_label)
        selector.addStretch(1)
        selector.addWidget(self.next_button)
        layout.addLayout(selector)

        grid = QGridLayout()
        self.session_button = QPushButton("Start test session")
        self.session_button.setMinimumHeight(48)
        self.session_button.clicked.connect(self.toggle_session)
        self.play_button = QPushButton("▶ Play pattern (loops)")
        self.play_button.setMinimumHeight(48)
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(lambda: self.engine.play_step(self.step))
        self.stop_button = QPushButton("■ STOP sound")
        self.stop_button.setObjectName("Danger")
        self.stop_button.setMinimumHeight(48)
        self.stop_button.clicked.connect(self.engine.stop_audio)
        grid.addWidget(self.session_button, 0, 0)
        grid.addWidget(self.play_button, 0, 1)
        grid.addWidget(self.stop_button, 0, 2)
        layout.addLayout(grid)

        self.status_label = QLabel("No test session")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.restore_label = QLabel("")
        self.restore_label.setWordWrap(True)
        layout.addWidget(self.restore_label)
        layout.addStretch(1)

        engine.status.connect(self.status_label.setText)
        engine.session_changed.connect(self.on_session_changed)
        engine.restore_result.connect(self.on_restore_result)
        self.update_step_label()

    def move_step(self, delta: int) -> None:
        was_playing = self.engine.playing_step is not None
        self.step = (self.step + delta) % len(audio.SPEAKER_STEPS)
        self.update_step_label()
        if was_playing:
            self.engine.play_step(self.step)

    def update_step_label(self) -> None:
        label, _, trim_code = audio.SPEAKER_STEPS[self.step]
        position = f"{self.step + 1}/{len(audio.SPEAKER_STEPS)}"
        self.speaker_label.setText(f"{label}  ({position})")
        self.speaker_label.setToolTip(f"Receiver trim channel: {trim_code}")

    def toggle_session(self) -> None:
        if self.engine.active:
            self.engine.end_session()
        else:
            self.restore_label.setText("")
            self.engine.start_session()

    def on_session_changed(self, active: bool) -> None:
        self.session_button.setText("End session && restore" if active else "Start test session")
        self.play_button.setEnabled(active)

    def on_restore_result(self, ok: bool, detail: str) -> None:
        color = "#007A3D" if ok else "#C21807"
        self.restore_label.setStyleSheet(f"color: {color}; font-weight: 700; border: none;")
        self.restore_label.setText(detail)
        if not ok:
            self.status_label.setText("Restore needs attention — see message above")
