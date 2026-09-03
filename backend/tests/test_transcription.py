"""Best-effort transcription test: skips (does not fail) when the Whisper
model can't be downloaded/loaded, since that depends on network access this
sandbox may not have. A green run here means real transcription actually
worked end to end; a skip is an honest "could not verify here", not a pass."""
import pytest

pytest.importorskip("faster_whisper")
np = pytest.importorskip("numpy")
sf = pytest.importorskip("soundfile")

from app.transcription import TranscriptionUnavailable, transcribe_audio  # noqa: E402

SR = 16000


def test_transcribe_audio_runs_end_to_end_or_skips_with_a_clear_reason(tmp_path):
    t = np.linspace(0, 2, SR * 2, endpoint=False)
    y = (0.1 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    path = tmp_path / "silence.wav"
    sf.write(str(path), y, SR)

    try:
        result = transcribe_audio(str(path), model_size="tiny", language="fr")
    except TranscriptionUnavailable as exc:
        pytest.skip(f"Whisper indisponible dans cet environnement: {exc}")
    else:
        assert result.language
        assert isinstance(result.lines, list)
