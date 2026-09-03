"""Optional audio feature extraction (tempo, energy envelope, section boundaries).

Requires `librosa` (listed in requirements.txt). Kept optional and imported
lazily so the rest of the app (and its tests) work without heavy audio deps
installed -- lyrics-only modes never need this module.
"""
from __future__ import annotations

from dataclasses import dataclass


class AudioAnalysisUnavailable(RuntimeError):
    """Raised when librosa/numpy are not installed but audio analysis was requested."""


@dataclass
class AudioSegment:
    start: float
    end: float
    energy: str  # "calme" | "modere" | "energique"


@dataclass
class AudioFeatures:
    duration: float
    tempo_bpm: float
    segments: list[AudioSegment]

    def suggested_genre_family(self) -> str:
        """A coarse tempo/energy-based nudge, not a genre classifier.

        The app always lets the user pick the real genre explicitly in the
        Director settings; this is only used to pre-select a sensible default.
        """
        avg_energetic = sum(1 for s in self.segments if s.energy == "energique")
        if self.tempo_bpm >= 118 and avg_energetic >= len(self.segments) / 2:
            return "afrobeat_amapiano_dance"
        if self.tempo_bpm <= 80:
            return "soul_gospel_ballade"
        if 80 < self.tempo_bpm < 118:
            return "jazz_rnb_zouk"
        return "pop_rock"


def analyze_audio_file(path: str, segment_seconds: float = 8.0) -> AudioFeatures:
    try:
        import librosa
        import numpy as np
    except ImportError as exc:  # pragma: no cover - exercised only without librosa
        raise AudioAnalysisUnavailable(
            "librosa/numpy ne sont pas installes. Installez-les (voir requirements.txt) "
            "pour activer l'analyse audio, ou utilisez un mode paroles-seules."
        ) from exc

    y, sr = librosa.load(path, sr=None, mono=True)
    duration = float(librosa.get_duration(y=y, sr=sr))
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    tempo_bpm = float(tempo) if tempo else 0.0

    rms = librosa.feature.rms(y=y)[0]
    hop_length = 512
    frame_times = librosa.frames_to_time(range(len(rms)), sr=sr, hop_length=hop_length)

    segments: list[AudioSegment] = []
    if duration > 0:
        n_segments = max(1, int(duration // segment_seconds))
        overall_median = float(np.median(rms)) if len(rms) else 0.0
        for i in range(n_segments):
            start = i * segment_seconds
            end = min(duration, start + segment_seconds)
            mask = (frame_times >= start) & (frame_times < end)
            local_rms = rms[mask]
            local_mean = float(np.mean(local_rms)) if len(local_rms) else 0.0
            if local_mean > overall_median * 1.15:
                energy = "energique"
            elif local_mean < overall_median * 0.85:
                energy = "calme"
            else:
                energy = "modere"
            segments.append(AudioSegment(start=start, end=end, energy=energy))

    return AudioFeatures(duration=duration, tempo_bpm=tempo_bpm, segments=segments)
