"""Real speech-to-text transcription of vocals, using faster-whisper
(a CTranslate2 port of OpenAI's Whisper model).

Production strategy (the point of this module, not just a dev convenience):
a lazy runtime download from the Hugging Face Hub on first request is NOT an
acceptable production behavior -- it makes the very first real user request
pay an unpredictable download latency, and it fails outright in any
deployment environment where that network path is unavailable at request
time (exactly what happens in this development sandbox: HIGGSFIELD.md
aside, Hugging Face Hub is blocked here, see README's "Limites connues").

So model resolution is decoupled from model download:
- WHISPER_MODEL_PATH, if set, must point to a CTranslate2 model directory
  already present on disk (baked into the deployment image at build time,
  e.g. via `huggingface-cli download` in a Docker build step, or synced
  from internal storage) -- faster-whisper loads it fully offline, and this
  is the path a real deployment should use.
- WHISPER_MODEL_SIZE (default "small") is used only as a fallback for local
  development convenience, where a by-name download from the Hub is fine.
- Manual lyrics remain the always-available fallback regardless: the
  pipeline only calls transcribe_audio() when no lyrics were provided (see
  pipeline.build_project), and a transcription failure here degrades to "no
  lyrics" rather than blocking the clip.

No paid transcription service is wired in; faster-whisper/Whisper stays a
free, open model either way -- only *how the weights reach the machine*
changes.
"""
from __future__ import annotations

import os
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


def _resolve_model_identifier(model_size: Optional[str]) -> str:
    """What to hand WhisperModel(): an explicit override, else a configured
    local (offline) model directory, else a by-name model for dev-time
    download. Never guesses a network path silently -- WHISPER_MODEL_PATH
    always wins when set."""
    if model_size:
        return model_size
    local_path = os.environ.get("WHISPER_MODEL_PATH")
    if local_path:
        return local_path
    return os.environ.get("WHISPER_MODEL_SIZE", "small")


def transcription_capability() -> str:
    """Cheap, no-model-load status check, useful for surfacing "will this
    even work" before committing to a transcription attempt:
    - "unavailable": faster-whisper isn't installed at all.
    - "offline_ready": WHISPER_MODEL_PATH is configured (should work with no
      network access).
    - "network_dependent": no local path configured -- first use will try
      to download a model by name (fine in dev, NOT a production guarantee).
    """
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return "unavailable"
    if os.environ.get("WHISPER_MODEL_PATH"):
        return "offline_ready"
    return "network_dependent"


def _get_model(model_size: Optional[str] = None):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscriptionUnavailable(
            "faster-whisper n'est pas installe. Installez-le (voir requirements.txt) "
            "pour activer la transcription automatique, ou saisissez les paroles manuellement."
        ) from exc

    identifier = _resolve_model_identifier(model_size)
    if identifier not in _model_cache:
        try:
            _model_cache[identifier] = WhisperModel(identifier, device="cpu", compute_type="int8")
        except Exception as exc:
            raise TranscriptionUnavailable(
                f"Impossible de charger le modele Whisper '{identifier}' "
                f"(reseau indisponible pour le telechargement initial, ou chemin local invalide): {exc}"
            ) from exc
    return _model_cache[identifier]


def transcribe_audio(
    audio_path: str, model_size: Optional[str] = None, language: Optional[str] = "fr"
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
