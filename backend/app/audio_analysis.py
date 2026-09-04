"""Real audio feature extraction: tempo, energy, and structural segmentation.

Requires `librosa`/`numpy` (listed in requirements.txt). Kept optional and
imported lazily so lyrics-only modes and the pure-logic test suite work
without these (heavier) dependencies installed.

Structural segmentation uses librosa's beat-synchronous agglomerative
clustering over a stacked MFCC+chroma feature matrix -- a standard MIR
technique (see librosa's own structural segmentation examples), not a
BPM/energy heuristic. It finds real change points in timbre and harmony
(verse/chorus/bridge-style transitions) directly from the waveform, with no
requirement for lyrics or an internet connection.
"""
from __future__ import annotations

from dataclasses import dataclass, field


class AudioAnalysisUnavailable(RuntimeError):
    """Raised when librosa/numpy are not installed but audio analysis was requested."""


@dataclass
class AudioSection:
    index: int
    start: float
    end: float
    energy: str  # "calme" | "modere" | "energique"
    local_tempo_bpm: float

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class AudioFeatures:
    duration: float
    tempo_bpm: float
    sections: list[AudioSection] = field(default_factory=list)

    def suggested_genre_family(self) -> str:
        """A coarse tempo/energy-based nudge -- NOT genre recognition.

        This exists only as a last-resort default when the real classifier
        in genre_classifier.py is unavailable (no model/network). It must
        never be presented to the user as "genre detecte".
        """
        if not self.sections:
            return "pop_rock"
        energetic_ratio = sum(1 for s in self.sections if s.energy == "energique") / len(self.sections)
        if self.tempo_bpm >= 118 and energetic_ratio >= 0.5:
            return "afrobeat_amapiano_dance"
        if self.tempo_bpm <= 80:
            return "soul_gospel_ballade"
        if 80 < self.tempo_bpm < 118:
            return "jazz_rnb_zouk"
        return "pop_rock"


def _scalar_tempo(tempo) -> float:
    """librosa's beat_track return type for tempo varies across versions (scalar vs 1-element array)."""
    try:
        return float(tempo)
    except TypeError:
        return float(tempo[0]) if len(tempo) else 0.0


def _classify_energy(local_mean: float, overall_median: float) -> str:
    if local_mean > overall_median * 1.15:
        return "energique"
    if local_mean < overall_median * 0.85:
        return "calme"
    return "modere"


def _target_section_count(duration: float, min_section_seconds: float, max_sections: int) -> int:
    if duration <= 0:
        return 1
    estimate = round(duration / min_section_seconds)
    return max(2, min(max_sections, estimate))


def detect_structural_boundaries(
    y, sr, min_section_seconds: float = 8.0, max_sections: int = 14
) -> list[float]:
    """Real structure detection: beat-synchronous MFCC+chroma agglomerative segmentation.

    Returns section boundary times in seconds, including 0.0 and the track
    duration as the first/last boundaries.
    """
    import librosa
    import numpy as np

    duration = float(librosa.get_duration(y=y, sr=sr))
    if duration <= 0:
        return [0.0, 0.0]

    hop_length = 512
    try:
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop_length)
    except Exception:
        beat_frames = None

    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=hop_length)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop_length)
    features = np.vstack([mfcc, chroma])

    if beat_frames is not None and len(beat_frames) >= 4:
        sync_features = librosa.util.sync(features, beat_frames, aggregate=np.median)
        boundary_frames_in_beats = True
    else:
        # Fall back to fixed-width frame windows if beat tracking finds too few beats.
        window = max(1, int((min_section_seconds / 2) / (hop_length / sr)))
        n_windows = max(1, features.shape[1] // window)
        trimmed = features[:, : n_windows * window]
        sync_features = trimmed.reshape(features.shape[0], n_windows, window).mean(axis=2)
        beat_frames = np.arange(n_windows) * window
        boundary_frames_in_beats = False

    k = _target_section_count(duration, min_section_seconds, max_sections)
    k = min(k, sync_features.shape[1])
    if k < 2:
        return [0.0, duration]

    boundary_indices = librosa.segment.agglomerative(sync_features, k)
    boundary_indices = sorted(set(int(i) for i in boundary_indices))

    if boundary_frames_in_beats:
        beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop_length)
        boundary_times = [float(beat_times[i]) if i < len(beat_times) else duration for i in boundary_indices]
    else:
        frame_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop_length)
        boundary_times = [float(frame_times[i]) if i < len(frame_times) else duration for i in boundary_indices]

    boundary_times = sorted(set([0.0] + boundary_times + [duration]))

    # Merge boundaries that are closer together than min_section_seconds, so
    # a track with subtle variation doesn't explode into tiny slivers.
    merged = [boundary_times[0]]
    for t in boundary_times[1:]:
        if t - merged[-1] >= min_section_seconds or t == duration:
            merged.append(t)
    if merged[-1] != duration:
        merged[-1] = duration
    if len(merged) < 2:
        merged = [0.0, duration]
    return merged


def decode_audio(path: str):
    """Decodes an audio file once to a mono float waveform + sample rate.

    Shared by analyze_audio_file() and genre_classifier.classify_genre(), so
    genre classification analyzes the exact same signal our own pipeline
    already decoded successfully, instead of depending on a second, less
    robust decoder (pydub/ffmpeg via pyAudioAnalysis) for the same file.
    """
    try:
        import librosa
    except ImportError as exc:  # pragma: no cover - exercised only without librosa
        raise AudioAnalysisUnavailable(
            "librosa n'est pas installe. Installez-le (voir requirements.txt) "
            "pour activer l'analyse audio, ou utilisez le mode paroles-seules."
        ) from exc
    return librosa.load(path, sr=None, mono=True)


def analyze_audio_file(path: str, min_section_seconds: float = 8.0, max_sections: int = 14) -> AudioFeatures:
    try:
        import librosa
        import numpy as np
    except ImportError as exc:  # pragma: no cover - exercised only without librosa
        raise AudioAnalysisUnavailable(
            "librosa/numpy ne sont pas installes. Installez-les (voir requirements.txt) "
            "pour activer l'analyse audio, ou utilisez le mode paroles-seules."
        ) from exc

    y, sr = decode_audio(path)
    duration = float(librosa.get_duration(y=y, sr=sr))
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    tempo_bpm = _scalar_tempo(tempo)

    boundaries = detect_structural_boundaries(y, sr, min_section_seconds=min_section_seconds, max_sections=max_sections)

    hop_length = 512
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    frame_times = librosa.frames_to_time(range(len(rms)), sr=sr, hop_length=hop_length)
    overall_median = float(np.median(rms)) if len(rms) else 0.0

    sections: list[AudioSection] = []
    for i in range(len(boundaries) - 1):
        start, end = boundaries[i], boundaries[i + 1]
        mask = (frame_times >= start) & (frame_times < end)
        local_rms = rms[mask]
        local_mean = float(np.mean(local_rms)) if len(local_rms) else 0.0
        energy = _classify_energy(local_mean, overall_median)

        y_section = y[int(start * sr) : int(end * sr)]
        local_tempo_bpm = tempo_bpm
        if len(y_section) > sr:  # need at least ~1s of audio to estimate a local tempo
            try:
                local_tempo, _ = librosa.beat.beat_track(y=y_section, sr=sr)
                local_tempo_scalar = _scalar_tempo(local_tempo)
                if local_tempo_scalar:
                    local_tempo_bpm = local_tempo_scalar
            except Exception:
                pass

        sections.append(
            AudioSection(index=i, start=round(start, 2), end=round(end, 2), energy=energy, local_tempo_bpm=round(local_tempo_bpm, 1))
        )

    return AudioFeatures(duration=duration, tempo_bpm=tempo_bpm, sections=sections)
