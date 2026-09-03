"""Verifies the real bundled genre classifier actually runs end to end
(feature extraction -> pretrained SVM -> real class probabilities) --
not a mock. Skipped if pyAudioAnalysis/sklearn aren't installed."""
import pytest

pytest.importorskip("pyAudioAnalysis")
np = pytest.importorskip("numpy")
sf = pytest.importorskip("soundfile")

from app.genre_classifier import (  # noqa: E402
    MODEL_LABEL_TO_APP_GENRE,
    classify_genre,
)

SR = 22050


@pytest.fixture
def synthetic_wav(tmp_path):
    t = np.linspace(0, 10, SR * 10, endpoint=False)
    y = (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    path = tmp_path / "tone.wav"
    sf.write(str(path), y, SR)
    return str(path)


def test_classify_genre_returns_one_of_the_six_real_model_classes(synthetic_wav):
    prediction = classify_genre(synthetic_wav)
    assert prediction.model_label in MODEL_LABEL_TO_APP_GENRE
    assert prediction.app_genre == MODEL_LABEL_TO_APP_GENRE[prediction.model_label]


def test_classify_genre_probabilities_are_real_and_sum_to_one(synthetic_wav):
    prediction = classify_genre(synthetic_wav)
    assert len(prediction.scores) == 6
    assert sum(prediction.scores.values()) == pytest.approx(1.0, abs=0.01)
    assert 0.0 <= prediction.confidence <= 1.0
    assert prediction.scores[prediction.model_label] == pytest.approx(prediction.confidence)
