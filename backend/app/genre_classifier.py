"""Real music genre classification -- not a BPM/energy heuristic.

Uses pyAudioAnalysis's bundled, pretrained SVM model (trained on real audio
features: MFCCs, spectral/chroma statistics, beat histogram). The model
ships inside the `pyAudioAnalysis` pip package itself, so it needs no
network access and no separate download -- verified end to end in this
sandbox against a synthetic test file (see tests/test_genre_classifier.py)
AND, since the classify_genre_from_signal() fix below, against a real MP3.

Honest limitation: the bundled model only distinguishes 6 broad families
(Blues, Classical, Electronic, Jazz, Rap, Rock) -- it cannot tell Afrobeat
from Amapiano from Makossa, because it was never trained on those classes.
It is offered as an automatic *suggestion* to pre-select one of those 6
families; regional genres in the Director settings remain a manual choice.
Never present its output as fine-grained genre recognition.

Decoding note: pyAudioAnalysis's own file reader (audioBasicIO.read_audio_file,
which shells out to pydub/ffmpeg for MP3) failed to decode a real-world test
file that our own librosa-based decoder handled correctly (see
audio_analysis.decode_audio). classify_genre_from_signal() below reimplements
the same feature-extraction + SVM-prediction steps pyAudioAnalysis's
file_classification() uses, but fed with our own already-decoded signal --
composing pyAudioAnalysis's public, stable functions (load_model,
MidTermFeatures.mid_feature_extraction, beat_extraction, classifier_wrapper)
rather than its fragile file-reading step. This is safe because
pyAudioAnalysis's own short-term feature extraction self-normalizes the
signal to [-1, 1] (ShortTermFeatures.dc_normalize divides by the signal's
own max amplitude), so it is agnostic to whether the input arrives as
int16 PCM (pyAudioAnalysis's native path) or as librosa's float32 [-1, 1]
waveform.
"""
from __future__ import annotations

from dataclasses import dataclass

from .audio_analysis import AudioAnalysisUnavailable, decode_audio

DEFAULT_APP_GENRE = "pop"

# The 6 real classes the bundled svm_rbf_musical_genre_6 model was trained on,
# mapped to genre keys with their own staging in storyboard.GENRE_STAGING.
MODEL_LABEL_TO_APP_GENRE = {
    "Blues": "blues",
    "Classical": "classique",
    "Electronic": "electro",
    "Jazz": "jazz",
    "Rap": "rap",
    "Rock": "rock",
}


class GenreClassificationUnavailable(RuntimeError):
    """Raised when pyAudioAnalysis/sklearn aren't installed or the model can't run."""


@dataclass
class GenrePrediction:
    app_genre: str
    model_label: str
    confidence: float
    scores: dict[str, float]


def _apply_numpy_2_compat_shim() -> None:
    """pyAudioAnalysis (last released 2020) still uses numpy.Inf/NaN, removed in numpy 2.0.

    Restoring these aliases is safe (numpy.inf/nan still exist) and is the
    workaround numpy's own migration guide suggests for unmaintained
    dependencies; it only patches names numpy itself dropped.
    """
    import numpy as np

    aliases = {"Inf": "inf", "Infinity": "inf", "NaN": "nan", "NAN": "nan", "PINF": "inf"}
    for old_name, new_name in aliases.items():
        if not hasattr(np, old_name):
            setattr(np, old_name, getattr(np, new_name))
    if not hasattr(np, "NINF"):
        np.NINF = -np.inf


def _model_path() -> str:
    import os

    import pyAudioAnalysis

    return os.path.join(os.path.dirname(pyAudioAnalysis.__file__), "data", "models", "svm_rbf_musical_genre_6")


def classify_genre_from_signal(y, sr: int) -> GenrePrediction:
    """Classifies an already-decoded mono waveform (as returned by
    audio_analysis.decode_audio) -- no second file decode, no dependency on
    pyAudioAnalysis's own fragile MP3 reader."""
    try:
        _apply_numpy_2_compat_shim()
        import numpy as np
        from pyAudioAnalysis import MidTermFeatures as aF
        from pyAudioAnalysis import audioTrainTest as aT
    except ImportError as exc:
        raise GenreClassificationUnavailable(
            "pyAudioAnalysis n'est pas installe. Installez-le (voir requirements.txt) "
            "pour activer la classification automatique de genre, ou choisissez le genre manuellement."
        ) from exc

    if y is None or len(y) == 0:
        raise GenreClassificationUnavailable("Signal audio vide, classification impossible.")

    try:
        classifier, mean, std, class_names, mid_window, mid_step, short_window, short_step, compute_beat = (
            aT.load_model(_model_path())
        )

        signal = np.asarray(y, dtype=np.float64)
        if signal.shape[0] / float(sr) < mid_window:
            mid_window = signal.shape[0] / float(sr)

        mid_features, short_features, _ = aF.mid_feature_extraction(
            signal, sr, mid_window * sr, mid_step * sr, round(sr * short_window), round(sr * short_step)
        )
        mid_features = mid_features.mean(axis=1)
        if compute_beat:
            beat, beat_conf = aF.beat_extraction(short_features, short_step)
            mid_features = np.append(mid_features, beat)
            mid_features = np.append(mid_features, beat_conf)
        feature_vector = (mid_features - mean) / std
        result_index, probabilities = aT.classifier_wrapper(classifier, "svm_rbf", feature_vector)
    except GenreClassificationUnavailable:
        raise
    except Exception as exc:
        raise GenreClassificationUnavailable(f"La classification de genre a echoue: {exc}") from exc

    scores = {name: float(p) for name, p in zip(class_names, probabilities)}
    model_label = class_names[int(result_index)]
    return GenrePrediction(
        app_genre=MODEL_LABEL_TO_APP_GENRE.get(model_label, DEFAULT_APP_GENRE),
        model_label=model_label,
        confidence=scores[model_label],
        scores=scores,
    )


def classify_genre(audio_path: str) -> GenrePrediction:
    """Decodes `audio_path` once (via audio_analysis.decode_audio, the same
    decoder the rest of the pipeline uses) and classifies the result."""
    try:
        y, sr = decode_audio(audio_path)
    except AudioAnalysisUnavailable as exc:
        raise GenreClassificationUnavailable(str(exc)) from exc
    return classify_genre_from_signal(y, sr)
