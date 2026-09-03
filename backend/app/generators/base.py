"""Provider-agnostic contract for image/video/audio generation.

Video generation here is image-to-video (generate a keyframe image, then
animate it) rather than text-to-video, because that's what the real
Higgsfield API actually offers (see higgsfield.py) -- the abstraction
follows the real provider's shape rather than an idealized one.
"""
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
    is_real: bool = False  # False for the mock/demo generator, True for a real paid provider

    @abstractmethod
    def generate_image(self, prompt: str, character_reference_id: Optional[str] = None) -> GeneratedAsset:
        ...

    @abstractmethod
    def generate_video_from_image(
        self,
        image_url: str,
        prompt: str,
        motion_hint: Optional[str] = None,
    ) -> GeneratedAsset:
        ...

    @abstractmethod
    def generate_audio(self, prompt: str, duration_seconds: float = 30.0) -> GeneratedAsset:
        ...

    def upload_file(self, local_path: str, content_type: str) -> str:
        """Uploads a local file to the provider's storage and returns a public URL."""
        raise NotImplementedError(f"{self.name} ne supporte pas l'upload de fichiers.")

    def create_character_reference(self, name: str, image_urls: list[str]) -> str:
        """Creates a reusable character reference from 1+ images; returns its id."""
        raise NotImplementedError(f"{self.name} ne supporte pas les personnages de reference.")

    def list_motions(self) -> list[dict]:
        return []
