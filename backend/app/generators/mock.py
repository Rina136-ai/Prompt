"""No-network generator used in tests and local development without an API key.

Produces deterministic placeholder asset descriptors so the rest of the
pipeline (storyboard -> generation -> assembly) can be exercised end to end
without spending credits or requiring network access.
"""
from __future__ import annotations

import hashlib
from typing import Optional

from .base import GeneratedAsset, Generator


def _fingerprint(prompt: str) -> str:
    return hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:10]


class MockGenerator(Generator):
    name = "mock"

    def generate_image(self, prompt: str, character_reference_url: Optional[str] = None) -> GeneratedAsset:
        fp = _fingerprint(prompt)
        return GeneratedAsset(kind="image", url=f"mock://image/{fp}.png", provider=self.name, job_id=fp)

    def generate_video(
        self,
        prompt: str,
        duration_seconds: float = 5.0,
        character_reference_url: Optional[str] = None,
    ) -> GeneratedAsset:
        fp = _fingerprint(prompt)
        return GeneratedAsset(kind="video", url=f"mock://video/{fp}.mp4", provider=self.name, job_id=fp)

    def generate_audio(self, prompt: str, duration_seconds: float = 30.0) -> GeneratedAsset:
        fp = _fingerprint(prompt)
        return GeneratedAsset(kind="audio", url=f"mock://audio/{fp}.wav", provider=self.name, job_id=fp)
