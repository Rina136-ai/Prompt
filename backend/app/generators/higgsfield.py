"""Real generation via the Higgsfield API (https://docs.higgsfield.ai).

Async job pattern: POST to create a generation, then poll by request id until
the job reaches a terminal state. Field/endpoint names follow Higgsfield's
public docs; if your account's API surface differs, adjust HIGGSFIELD_*
constants below rather than the polling logic.
"""
from __future__ import annotations

import time
from typing import Optional

import requests

from .base import GeneratedAsset, GenerationError, Generator

DEFAULT_BASE_URL = "https://api.higgsfield.ai"
GENERATIONS_PATH = "/v1/generations"
TERMINAL_SUCCESS = {"succeeded", "completed", "success"}
TERMINAL_FAILURE = {"failed", "error", "cancelled"}

DEFAULT_IMAGE_MODEL = "soul_2"
DEFAULT_VIDEO_MODEL = "seedance_2_5"
DEFAULT_AUDIO_MODEL = "seed_audio"


class HiggsfieldGenerator(Generator):
    name = "higgsfield"

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        poll_interval_seconds: float = 3.0,
        poll_timeout_seconds: float = 180.0,
        session: Optional[requests.Session] = None,
    ):
        if not api_key:
            raise GenerationError("HIGGSFIELD_API_KEY manquant.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.poll_interval_seconds = poll_interval_seconds
        self.poll_timeout_seconds = poll_timeout_seconds
        self.session = session or requests.Session()

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _submit(self, payload: dict) -> str:
        response = self.session.post(
            f"{self.base_url}{GENERATIONS_PATH}", json=payload, headers=self._headers(), timeout=30
        )
        if not response.ok:
            raise GenerationError(f"Higgsfield a refuse la requete ({response.status_code}): {response.text[:300]}")
        data = response.json()
        request_id = data.get("id") or data.get("request_id") or data.get("job_id")
        if not request_id:
            raise GenerationError(f"Reponse Higgsfield sans identifiant de job: {data}")
        return request_id

    def _poll(self, request_id: str) -> dict:
        deadline = time.monotonic() + self.poll_timeout_seconds
        while time.monotonic() < deadline:
            response = self.session.get(
                f"{self.base_url}{GENERATIONS_PATH}/{request_id}", headers=self._headers(), timeout=30
            )
            if not response.ok:
                raise GenerationError(f"Echec du suivi de job Higgsfield ({response.status_code}): {response.text[:300]}")
            data = response.json()
            status = str(data.get("status", "")).lower()
            if status in TERMINAL_SUCCESS:
                return data
            if status in TERMINAL_FAILURE:
                raise GenerationError(f"Job Higgsfield {request_id} en echec: {data.get('error', data)}")
            time.sleep(self.poll_interval_seconds)
        raise GenerationError(f"Timeout en attendant le job Higgsfield {request_id}")

    def _extract_url(self, result: dict) -> str:
        for key in ("output_url", "url", "result_url"):
            if result.get(key):
                return result[key]
        outputs = result.get("outputs") or result.get("output")
        if isinstance(outputs, list) and outputs:
            first = outputs[0]
            return first.get("url") if isinstance(first, dict) else str(first)
        raise GenerationError(f"Impossible de trouver l'URL de resultat dans la reponse: {result}")

    def generate_image(self, prompt: str, character_reference_url: Optional[str] = None) -> GeneratedAsset:
        payload: dict = {"model": DEFAULT_IMAGE_MODEL, "prompt": prompt}
        if character_reference_url:
            payload["reference_image_urls"] = [character_reference_url]
        request_id = self._submit(payload)
        result = self._poll(request_id)
        return GeneratedAsset(kind="image", url=self._extract_url(result), provider=self.name, job_id=request_id)

    def generate_video(
        self,
        prompt: str,
        duration_seconds: float = 5.0,
        character_reference_url: Optional[str] = None,
    ) -> GeneratedAsset:
        payload: dict = {"model": DEFAULT_VIDEO_MODEL, "prompt": prompt, "duration": duration_seconds}
        if character_reference_url:
            payload["image_url"] = character_reference_url
        request_id = self._submit(payload)
        result = self._poll(request_id)
        return GeneratedAsset(kind="video", url=self._extract_url(result), provider=self.name, job_id=request_id)

    def generate_audio(self, prompt: str, duration_seconds: float = 30.0) -> GeneratedAsset:
        payload = {"model": DEFAULT_AUDIO_MODEL, "prompt": prompt, "duration": duration_seconds}
        request_id = self._submit(payload)
        result = self._poll(request_id)
        return GeneratedAsset(kind="audio", url=self._extract_url(result), provider=self.name, job_id=request_id)
