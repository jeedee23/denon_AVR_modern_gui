"""Multichannel test-tone generation and playback over the HDMI device.

Playback requires the optional sounddevice/numpy stack; everything degrades
gracefully (with a clear message) when audio output is unavailable.
"""

from __future__ import annotations

import threading

try:
    import numpy as np
    import sounddevice as sd

    AUDIO_AVAILABLE = True
except (ImportError, OSError):  # pragma: no cover - depends on host audio stack
    np = None
    sd = None
    AUDIO_AVAILABLE = False

SAMPLE_RATE = 48000
CHANNEL_COUNT = 8  # Windows 7.1 PCM order: FL FR C LFE BL BR SL SR

# Serializes PortAudio teardown/reinit against any other native audio call.
_pa_lock = threading.Lock()

# (UI label, 7.1 channel index, trim code shown next to it)
# Owner observation 2026-11-28: this AVR has no surround-back speakers, so the
# BL/BR PCM channels fold into the front speakers; the Surround Dolby pair
# (SDL/SDR, hung ~6 m back behind the surrounds) is not addressable over
# HDMI PCM.
SPEAKER_STEPS = (
    ("Front Left", 0, "FL"),
    ("Front Right", 1, "FR"),
    ("Center", 2, "C"),
    ("Surround Left", 6, "SL"),
    ("Surround Right", 7, "SR"),
    ("Back L probe (folds into front)", 4, "—"),
    ("Back R probe (folds into front)", 5, "—"),
    ("Subwoofer sweep", 3, "SW"),
)

TONE_HZ = 425.0
TONE_SECONDS = 3.0
SWEEP_SECONDS = 6.0
SWEEP_START_HZ = 100.0
SWEEP_END_HZ = 50.0

# Intermittent identification pattern: "ta ta ta ta" at four frequencies.
PATTERN_HZ = (430.0, 800.0, 1000.0, 200.0)
BURST_SECONDS = 0.18
GAP_SECONDS = 0.14


class AudioUnavailableError(RuntimeError):
    pass


def _require_audio() -> None:
    if not AUDIO_AVAILABLE:
        raise AudioUnavailableError(
            "Audio playback needs the sounddevice and numpy packages and a working output device"
        )


def refresh_devices() -> None:
    """Re-enumerate audio devices so HDMI EDID changes are picked up live.

    Must only run when no stream is in use: tearing PortAudio down while
    another thread touches a stream crashes the process natively.
    """
    if not AUDIO_AVAILABLE:
        return
    with _pa_lock:
        try:
            sd.stop()
            sd._terminate()
            sd._initialize()
        except Exception:  # pragma: no cover - host specific
            pass


def find_output_device(name_hint: str = "DENON") -> tuple[int | None, int]:
    """Best output device matching the hint and its usable channel count.

    Prefers the WASAPI entry with the most channels. Windows can fall back to
    stereo for an HDMI endpoint after EDID renegotiation; callers must handle
    a channel count below CHANNEL_COUNT.
    """
    _require_audio()
    refresh_devices()
    try:
        apis = sd.query_hostapis()
        wasapi = next((i for i, api in enumerate(apis) if "WASAPI" in api["name"]), None)
        best: tuple[int, int, int] | None = None  # (channels, wasapi?, index)
        for index, device in enumerate(sd.query_devices()):
            if name_hint.upper() not in device["name"].upper():
                continue
            channels = min(CHANNEL_COUNT, int(device["max_output_channels"]))
            if channels < 1:
                continue
            rank = (channels, 1 if device["hostapi"] == wasapi else 0, -index)
            if best is None or rank > (best[0], best[1], -best[2]):
                best = (channels, rank[1], index)
        if best is not None:
            return best[2], best[0]
    except Exception:  # pragma: no cover - host specific
        pass
    return None, 2


def _fade(signal, ms: float = 30.0):
    n = int(SAMPLE_RATE * ms / 1000)
    envelope = np.ones(len(signal))
    envelope[:n] = np.linspace(0.0, 1.0, n)
    envelope[-n:] = np.linspace(1.0, 0.0, n)
    return signal * envelope


def build_tone(amplitude_dbfs: float = -20.0):
    _require_audio()
    amplitude = 10 ** (amplitude_dbfs / 20)
    t = np.arange(int(SAMPLE_RATE * TONE_SECONDS)) / SAMPLE_RATE
    return _fade(amplitude * np.sin(2 * np.pi * TONE_HZ * t))


def build_sweep(amplitude_dbfs: float = -20.0):
    _require_audio()
    amplitude = 10 ** (amplitude_dbfs / 20)
    t = np.arange(int(SAMPLE_RATE * SWEEP_SECONDS)) / SAMPLE_RATE
    freq = SWEEP_START_HZ * (SWEEP_END_HZ / SWEEP_START_HZ) ** (t / SWEEP_SECONDS)
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    return _fade(amplitude * np.sin(phase))


def build_pattern(amplitude_dbfs: float = -20.0):
    """One 'ta ta ta ta' cycle: short bursts at 430/800/1000/200 Hz with gaps."""
    _require_audio()
    amplitude = 10 ** (amplitude_dbfs / 20)
    pieces = []
    gap = np.zeros(int(SAMPLE_RATE * GAP_SECONDS))
    for hz in PATTERN_HZ:
        t = np.arange(int(SAMPLE_RATE * BURST_SECONDS)) / SAMPLE_RATE
        pieces.append(_fade(amplitude * np.sin(2 * np.pi * hz * t), ms=12.0))
        pieces.append(gap)
    return np.concatenate(pieces)


class TonePlayer:
    """Plays a mono signal on one channel of the multichannel output."""

    def __init__(self, device: int | None = None, channels: int = CHANNEL_COUNT) -> None:
        _require_audio()
        self.device = device
        self.channels = max(1, min(CHANNEL_COUNT, channels))
        self._stop = threading.Event()

    def play_on_channel(self, mono, channel: int) -> bool:
        """Blocking single play; returns False when stopped early."""
        self._check_channel(channel)
        self._stop.clear()
        return self._play_once(mono, channel)

    def play_loop(self, mono, channel: int, should_continue=None) -> None:
        """Repeat the signal until stop() is called or should_continue() is False."""
        self._check_channel(channel)
        self._stop.clear()
        while not self._stop.is_set():
            if should_continue is not None and not should_continue():
                break
            if not self._play_once(mono, channel, should_continue):
                break

    def _check_channel(self, channel: int) -> None:
        if channel >= self.channels:
            raise AudioUnavailableError(
                f"This speaker needs output channel {channel + 1}, but Windows currently "
                f"exposes only {self.channels} channel(s) on the HDMI device. Set the "
                "speaker configuration of '1 - DENON-AVR' to 7.1 Surround in Windows "
                "Sound settings, then try again."
            )

    def _play_once(self, mono, channel: int, should_continue=None) -> bool:
        frames = np.zeros((len(mono), self.channels), dtype=np.float32)
        frames[:, channel] = mono.astype(np.float32)
        with _pa_lock:
            sd.play(frames, SAMPLE_RATE, device=self.device)
        try:
            while sd.get_stream().active:
                if self._stop.wait(0.05) or (
                    should_continue is not None and not should_continue()
                ):
                    sd.stop()
                    return False
        except Exception:  # pragma: no cover - host specific
            return False
        return True

    def stop(self) -> None:
        """Request stop; only the playback thread touches PortAudio.

        Calling sd.stop() from another thread (e.g. the GUI) races the
        playback thread's sd.play()/get_stream() and can crash natively, so
        this merely signals; the playback loop reacts within ~50 ms.
        """
        self._stop.set()
