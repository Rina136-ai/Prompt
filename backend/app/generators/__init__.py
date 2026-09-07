import os

from .base import GeneratedAsset, GenerationError, Generator
from .higgsfield import DEFAULT_VIDEO_MODEL, HiggsfieldGenerator
from .mock import MockGenerator


def _read_credentials() -> tuple[str, str] | None:
    combined = os.environ.get("HIGGSFIELD_CREDENTIALS")
    if combined and ":" in combined:
        key_id, key_secret = combined.split(":", 1)
        return key_id, key_secret
    key_id = os.environ.get("HIGGSFIELD_KEY_ID")
    key_secret = os.environ.get("HIGGSFIELD_KEY_SECRET")
    if key_id and key_secret:
        return key_id, key_secret
    return None


def get_generator() -> Generator:
    """Picks the real Higgsfield generator when credentials are set, else the mock (MODE DEMO)."""
    credentials = _read_credentials()
    if credentials:
        base_url = os.environ.get("HIGGSFIELD_BASE_URL", "https://platform.higgsfield.ai")
        video_model = os.environ.get("HIGGSFIELD_VIDEO_MODEL") or DEFAULT_VIDEO_MODEL
        return HiggsfieldGenerator(
            key_id=credentials[0], key_secret=credentials[1], base_url=base_url, video_model=video_model
        )
    return MockGenerator()


__all__ = ["GeneratedAsset", "GenerationError", "Generator", "HiggsfieldGenerator", "MockGenerator", "get_generator"]
