"""No-network generator used in tests, local development, and the UI's "MODE DEMO".

Produces deterministic placeholder asset descriptors so the rest of the
pipeline (storyboard -> generation -> assembly) can be exercised end to end
without spending credits, without an API key, and without network access.
This is NEVER real AI generation -- callers (the API layer, the frontend)
must surface `provider == "mock"` as a clearly labeled demo/simulation.
"""
from __future__ import annotations

import hashlib
from typing import Optional

from .base import GeneratedAsset, Generator


def _fingerprint(prompt: str) -> str:
    return hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:10]


class MockGenerator(Generator):
    name = "mock"
    is_real = False

    def generate_image(self, prompt: str, character_reference_id: Optional[str] = None) -> GeneratedAsset:
        fp = _fingerprint(prompt)
        return GeneratedAsset(kind="image", url=f"mock://image/{fp}.png", provider=self.name, job_id=fp)

    def generate_video_from_image(
        self,
        image_url: str,
        prompt: str,
        motion_hint: Optional[str] = None,
    ) -> GeneratedAsset:
        fp = _fingerprint(image_url + prompt)
        return GeneratedAsset(kind="video", url=f"mock://video/{fp}.mp4", provider=self.name, job_id=fp)

    def generate_audio(self, prompt: str, duration_seconds: float = 30.0) -> GeneratedAsset:
        fp = _fingerprint(prompt)
        return GeneratedAsset(kind="audio", url=f"mock://audio/{fp}.wav", provider=self.name, job_id=fp)

    def upload_file(self, local_path: str, content_type: str) -> str:
        fp = hashlib.sha1(local_path.encode("utf-8")).hexdigest()[:10]
        return f"mock://upload/{fp}"

    def create_character_reference(self, name: str, image_urls: list[str]) -> str:
        fp = hashlib.sha1((name + "|".join(image_urls)).encode("utf-8")).hexdigest()[:10]
        return f"mock-ref-{fp}"

    def list_motions(self) -> list[dict]:
        return [
            {"id": "mock-zoom-in", "name": "Zoom In"},
            {"id": "mock-dolly", "name": "Dolly"},
            {"id": "mock-drone", "name": "Drone / Aerial"},
            {"id": "mock-pan", "name": "Pan"},
        ]
