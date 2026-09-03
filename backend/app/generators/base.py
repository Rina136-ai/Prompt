"""Provider-agnostic contract for image/video/audio generation."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class GeneratedAsset:
    kind: str  # "image" | "video" | "audio"
    url: str
    provider: str
    job_id: Optional[str] = None
    local_path: Optional[str] = None


class GenerationError(RuntimeError):
    pass


class Generator(ABC):
    name: str = "generator"

    @abstractmethod
    def generate_image(self, prompt: str, character_reference_url: Optional[str] = None) -> GeneratedAsset:
        ...

    @abstractmethod
    def generate_video(
        self,
        prompt: str,
        duration_seconds: float = 5.0,
        character_reference_url: Optional[str] = None,
    ) -> GeneratedAsset:
        ...

    @abstractmethod
    def generate_audio(self, prompt: str, duration_seconds: float = 30.0) -> GeneratedAsset:
        ...
