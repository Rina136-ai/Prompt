"""Real music genre classification -- not a BPM/energy heuristic.

Uses pyAudioAnalysis's bundled, pretrained SVM model (trained on real audio
features: MFCCs, spectral/chroma statistics, beat histogram). The model
ships inside the `pyAudioAnalysis` pip package itself, so it needs no
network access and no separate download -- verified end to end in this
sandbox against a synthetic test file (see tests/test_genre_classifier.py).

Honest limitation: the bundled model only distinguishes 6 broad families
(Blues, Classical, Electronic, Jazz, Rap, Rock) -- it cannot tell Afrobeat
from Amapiano from Makossa, because it was never trained on those classes.
It is offered as an automatic *suggestion* to pre-select one of those 6
families; regional genres in the Director settings remain a manual choice.
Never present its output as fine-grained genre recognition.
"""
from __future__ import annotations

from dataclasses import dataclass


class GenreClassificationUnavailable(RuntimeError):
    """Raised when pyAudioAnalysis/sklearn aren't installed or the model can't load."""


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


def classify_genre(audio_path: str) -> GenrePrediction:
    try:
        _apply_numpy_2_compat_shim()
        from pyAudioAnalysis import audioTrainTest as aT
        import pyAudioAnalysis
    except ImportError as exc:
        raise GenreClassificationUnavailable(
            "pyAudioAnalysis n'est pas installe. Installez-le (voir requirements.txt) "
            "pour activer la classification automatique de genre, ou choisissez le genre manuellement."
        ) from exc

    import os

    model_path = os.path.join(os.path.dirname(pyAudioAnalysis.__file__), "data", "models", "svm_rbf_musical_genre_6")
    try:
        result_index, probabilities, class_names = aT.file_classification(audio_path, model_path, "svm_rbf")
    except Exception as exc:
        raise GenreClassificationUnavailable(f"La classification de genre a echoue: {exc}") from exc

    scores = {name: float(p) for name, p in zip(class_names, probabilities)}
    model_label = class_names[int(result_index)]
    return GenrePrediction(
        app_genre=MODEL_LABEL_TO_APP_GENRE.get(model_label, "pop"),
        model_label=model_label,
        confidence=scores[model_label],
        scores=scores,
    )
