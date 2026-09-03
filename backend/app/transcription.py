"""Real speech-to-text transcription of vocals, using faster-whisper
(a CTranslate2 port of OpenAI's Whisper model).

Model weights are fetched from the Hugging Face Hub on first use and cached
locally afterwards. This development sandbox blocks that download at the
network level (see README's "Limites connues"), so this module could not be
exercised end to end here -- tests/test_transcription.py skips with a clear
reason rather than fabricating a pass when that happens. On a machine with
normal internet access it downloads a real Whisper checkpoint once and then
works fully offline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


class TranscriptionUnavailable(RuntimeError):
    pass


@dataclass
class TranscribedLine:
    start: float
    end: float
    text: str


@dataclass
class TranscriptionResult:
    language: str
    lines: list[TranscribedLine] = field(default_factory=list)

    def full_text(self) -> str:
        return "\n".join(line.text for line in self.lines)


_model_cache: dict[str, object] = {}


def _get_model(model_size: str = "small"):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscriptionUnavailable(
            "faster-whisper n'est pas installe. Installez-le (voir requirements.txt) "
            "pour activer la transcription automatique, ou saisissez les paroles manuellement."
        ) from exc

    if model_size not in _model_cache:
        try:
            _model_cache[model_size] = WhisperModel(model_size, device="cpu", compute_type="int8")
        except Exception as exc:
            raise TranscriptionUnavailable(
                f"Impossible de charger le modele Whisper '{model_size}' "
                f"(reseau indisponible pour le telechargement initial, ou modele non mis en cache): {exc}"
            ) from exc
    return _model_cache[model_size]


def transcribe_audio(
    audio_path: str, model_size: str = "small", language: Optional[str] = "fr"
) -> TranscriptionResult:
    model = _get_model(model_size)
    try:
        segments, info = model.transcribe(audio_path, language=language, vad_filter=True)
        lines = [
            TranscribedLine(start=round(seg.start, 2), end=round(seg.end, 2), text=seg.text.strip())
            for seg in segments
        ]
    except Exception as exc:
        raise TranscriptionUnavailable(f"La transcription a echoue: {exc}") from exc
    return TranscriptionResult(language=info.language, lines=lines)
