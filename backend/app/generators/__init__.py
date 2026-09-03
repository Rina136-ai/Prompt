import os

from .base import GeneratedAsset, GenerationError, Generator
from .higgsfield import HiggsfieldGenerator
from .mock import MockGenerator


def get_generator() -> Generator:
    """Picks the Higgsfield generator when HIGGSFIELD_API_KEY is set, else falls back to the mock."""
    api_key = os.environ.get("HIGGSFIELD_API_KEY")
    if api_key:
        base_url = os.environ.get("HIGGSFIELD_BASE_URL", "https://api.higgsfield.ai")
        return HiggsfieldGenerator(api_key=api_key, base_url=base_url)
    return MockGenerator()


__all__ = ["GeneratedAsset", "GenerationError", "Generator", "HiggsfieldGenerator", "MockGenerator", "get_generator"]
