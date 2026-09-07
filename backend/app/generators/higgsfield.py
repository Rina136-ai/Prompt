"""Real generation via the Higgsfield v2 API.

IMPORTANT -- provenance of this contract, re-verified before the first real
connection attempt: docs.higgsfield.ai, platform.higgsfield.ai and
api.higgsfield.ai are all still unreachable from this development sandbox
(network egress to the higgsfield.ai domain is blocked here). What IS
reachable is the npm registry, so this contract is verified directly
against the official `@higgsfield/client` package source (v0.2.1, pulled
fresh from registry.npmjs.org as a tarball -- both the deprecated v1
client, dist/client.js, and the current recommended v2 client,
dist/v2/client.js, were read in full), not just prose docs or a guess:

- Base URL: https://platform.higgsfield.ai
- Auth header (v2, current/recommended): "Authorization: Key <KEY_ID>:<KEY_SECRET>"
- POST <endpoint> with the input parameters as the raw JSON body (not
  wrapped in {"params": ...} -- that wrapping is a v1-client-only
  convention we deliberately don't use). Confirmed working for
  /v1/image2video/dop specifically in the current v2 README example.
- Response: {"status", "request_id", "images": [{"url"}], "video": {"url"}}
- Poll GET /requests/{request_id}/status until status is one of
  completed | nsfw | failed | canceled (the v2 client's own poller only
  checks for completed/nsfw/failed -- we also stop on canceled, which is
  strictly safer, not a deviation worth "fixing away")
- File upload: POST /files/generate-upload-url {"content_type"} ->
  {"upload_url", "public_url"}, then PUT the bytes to upload_url
- Character consistency ("SoulId"): POST /v1/custom-references
  {"name", "input_images": [{"type": "image_url", "image_url": ...}]},
  then poll GET /v1/custom-references/{id} until status is
  completed | failed; use the id as `custom_reference_id` in later
  /v1/text2image/soul calls. Confirmed from source (dist/types.d.ts) that
  SoulIdCreateData takes ANY number of input_images (no 5-20 photo minimum,
  no training step) -- this is already the instant, single-image reference
  mechanism, not a heavy "Soul training" flow. Higgsfield's own newer
  consumer product surface (Soul 2.0 / Soul Cinema "Train Soul", Seedance
  2.0's "Reference Elements") is visible through their MCP/app catalog but
  has NO verified public REST contract reachable from this sandbox -- so,
  deliberately, none of those newer model ids are wired in here. Wiring
  one in without being able to verify its real endpoint/payload would mean
  shipping a guess dressed up as a fix, which is worse than leaving this
  documented gap in place.
- DoP (image-to-video) model tiers, confirmed from source
  (dist/helpers.js DoPModel enum): "dop-lite" (basic speed/quality),
  "dop-turbo" (2x speed, priority queue), "dop-standard" (highest quality,
  priority queue). No pricing table is exposed anywhere we can reach, but
  "lite" is the one described as the basic/cheapest tier, so it's the
  default here for a first real test -- override via HIGGSFIELD_VIDEO_MODEL
  if a different tier is wanted later.

No live call has been made against this contract in this sandbox: there is
no API key configured here, and the host is blocked anyway. Before trusting
this in production, run `tests/integration/test_higgsfield_live.py` with a
real HIGGSFIELD_KEY_ID/HIGGSFIELD_KEY_SECRET (see that file's docstring). If
Higgsfield changes their API, that live test -- not this docstring -- is
the source of truth.
"""
from __future__ import annotations

import time
from typing import Optional

import requests

from .base import GeneratedAsset, GenerationError, Generator

BASE_URL = "https://platform.higgsfield.ai"
TERMINAL_STATUSES = {"completed", "nsfw", "failed", "canceled"}

TEXT2IMAGE_ENDPOINT = "/v1/text2image/soul"
IMAGE2VIDEO_ENDPOINT = "/v1/image2video/dop"
CUSTOM_REFERENCE_ENDPOINT = "/v1/custom-references"
UPLOAD_URL_ENDPOINT = "/files/generate-upload-url"
MOTIONS_ENDPOINT = "/v1/motions"

DEFAULT_IMAGE_SIZE = "1536x1536"
DEFAULT_IMAGE_QUALITY = "1080p"

# The 3 real DoP tiers (confirmed from @higgsfield/client's DoPModel enum).
# "lite" is the basic/cheapest one -- the right default for a first real
# test, per the same "most appropriate, not most expensive" principle used
# to pick DoP itself over an unverified newer model.
VIDEO_MODEL_LITE = "dop-lite"
VIDEO_MODEL_TURBO = "dop-turbo"
VIDEO_MODEL_STANDARD = "dop-standard"
VALID_VIDEO_MODELS = {VIDEO_MODEL_LITE, VIDEO_MODEL_TURBO, VIDEO_MODEL_STANDARD}
DEFAULT_VIDEO_MODEL = VIDEO_MODEL_LITE


class HiggsfieldGenerator(Generator):
    name = "higgsfield"
    is_real = True

    def __init__(
        self,
        key_id: str,
        key_secret: str,
        base_url: str = BASE_URL,
        video_model: str = DEFAULT_VIDEO_MODEL,
        poll_interval_seconds: float = 3.0,
        poll_timeout_seconds: float = 300.0,
        session: Optional[requests.Session] = None,
    ):
        if not key_id or not key_secret:
            raise GenerationError(
                "HIGGSFIELD_KEY_ID et HIGGSFIELD_KEY_SECRET sont requis pour la generation reelle."
            )
        if video_model not in VALID_VIDEO_MODELS:
            raise GenerationError(
                f"Modele video DoP inconnu: {video_model!r}. Valeurs valides: {sorted(VALID_VIDEO_MODELS)}."
            )
        self.base_url = base_url.rstrip("/")
        self.video_model = video_model
        self.poll_interval_seconds = poll_interval_seconds
        self.poll_timeout_seconds = poll_timeout_seconds
        self.session = session or requests.Session()
        self._headers = {
            "Authorization": f"Key {key_id}:{key_secret}",
            "Content-Type": "application/json",
        }

    def _raise_for_errors(self, response: requests.Response) -> None:
        if response.ok:
            return
        status = response.status_code
        try:
            detail = response.json().get("detail", response.text[:300])
        except ValueError:
            detail = response.text[:300]
        if status == 401:
            raise GenerationError("Identifiants Higgsfield invalides (401 Unauthorized).")
        if status == 403:
            raise GenerationError("Credits Higgsfield insuffisants (403 Forbidden).")
        if status in (400, 422):
            raise GenerationError(f"Requete Higgsfield invalide ({status}): {detail}")
        raise GenerationError(f"Erreur API Higgsfield ({status}): {detail}")

    def _post(self, path: str, json_body: dict) -> dict:
        response = self.session.post(f"{self.base_url}{path}", json=json_body, headers=self._headers, timeout=30)
        self._raise_for_errors(response)
        return response.json()

    def _get(self, path: str) -> dict:
        response = self.session.get(f"{self.base_url}{path}", headers=self._headers, timeout=30)
        self._raise_for_errors(response)
        return response.json()

    def _subscribe(self, endpoint: str, input_payload: dict) -> dict:
        data = self._post(endpoint, input_payload)
        request_id = data.get("request_id")
        if not request_id:
            raise GenerationError(f"Reponse Higgsfield sans request_id: {data}")
        return self._poll_request(request_id)

    def _poll_request(self, request_id: str) -> dict:
        deadline = time.monotonic() + self.poll_timeout_seconds
        while time.monotonic() < deadline:
            data = self._get(f"/requests/{request_id}/status")
            status = data.get("status")
            if status in TERMINAL_STATUSES:
                if status == "failed":
                    raise GenerationError(f"Generation Higgsfield en echec (request {request_id}): {data}")
                if status == "nsfw":
                    raise GenerationError(f"Contenu rejete par la moderation Higgsfield (request {request_id}).")
                if status == "canceled":
                    raise GenerationError(f"Job Higgsfield annule (request {request_id}).")
                return data
            time.sleep(self.poll_interval_seconds)
        raise GenerationError(f"Timeout en attendant le job Higgsfield {request_id}")

    def _extract_media_url(self, result: dict) -> str:
        images = result.get("images") or []
        if images:
            return images[0]["url"]
        video = result.get("video")
        if video and video.get("url"):
            return video["url"]
        raise GenerationError(f"Aucune URL de resultat dans la reponse Higgsfield: {result}")

    def upload_file(self, local_path: str, content_type: str) -> str:
        data = self._post(UPLOAD_URL_ENDPOINT, {"content_type": content_type})
        upload_url, public_url = data["upload_url"], data["public_url"]
        with open(local_path, "rb") as f:
            put_response = self.session.put(upload_url, data=f.read(), headers={"Content-Type": content_type}, timeout=120)
        if not put_response.ok:
            raise GenerationError(f"Echec de l'upload vers le CDN Higgsfield ({put_response.status_code}).")
        return public_url

    def create_character_reference(self, name: str, image_urls: list[str]) -> str:
        payload = {"name": name, "input_images": [{"type": "image_url", "image_url": u} for u in image_urls]}
        data = self._post(CUSTOM_REFERENCE_ENDPOINT, payload)
        reference_id = data.get("id")
        if not reference_id:
            raise GenerationError(f"Reponse Higgsfield sans id de reference: {data}")

        deadline = time.monotonic() + self.poll_timeout_seconds
        while time.monotonic() < deadline:
            status_data = self._get(f"{CUSTOM_REFERENCE_ENDPOINT}/{reference_id}")
            status = status_data.get("status")
            if status == "completed":
                return reference_id
            if status == "failed":
                raise GenerationError(f"Echec de creation du personnage de reference {reference_id}.")
            time.sleep(self.poll_interval_seconds)
        raise GenerationError(f"Timeout en attendant la creation du personnage de reference {reference_id}")

    def list_motions(self) -> list[dict]:
        return self._get(MOTIONS_ENDPOINT)

    def generate_image(self, prompt: str, character_reference_id: Optional[str] = None) -> GeneratedAsset:
        payload: dict = {
            "prompt": prompt,
            "width_and_height": DEFAULT_IMAGE_SIZE,
            "quality": DEFAULT_IMAGE_QUALITY,
            "batch_size": 1,
        }
        if character_reference_id:
            payload["custom_reference_id"] = character_reference_id
            payload["custom_reference_strength"] = 0.85
        result = self._subscribe(TEXT2IMAGE_ENDPOINT, payload)
        url = self._extract_media_url(result)
        return GeneratedAsset(kind="image", url=url, provider=self.name, job_id=result.get("request_id"))

    def generate_video_from_image(
        self,
        image_url: str,
        prompt: str,
        motion_hint: Optional[str] = None,
    ) -> GeneratedAsset:
        payload: dict = {
            "model": self.video_model,
            "prompt": prompt,
            "input_images": [{"type": "image_url", "image_url": image_url}],
        }
        motion_id = self._resolve_motion_id(motion_hint) if motion_hint else None
        if motion_id:
            payload["motions"] = [{"id": motion_id, "strength": 1.0}]
        result = self._subscribe(IMAGE2VIDEO_ENDPOINT, payload)
        url = self._extract_media_url(result)
        return GeneratedAsset(kind="video", url=url, provider=self.name, job_id=result.get("request_id"))

    def _resolve_motion_id(self, motion_hint: str) -> Optional[str]:
        try:
            motions = self.list_motions()
        except GenerationError:
            return None
        hint = motion_hint.lower()
        for motion in motions:
            if hint in str(motion.get("name", "")).lower():
                return motion.get("id")
        return None

    def generate_audio(self, prompt: str, duration_seconds: float = 30.0) -> GeneratedAsset:
        raise GenerationError(
            "Higgsfield ne propose pas de generation de musique originale a partir de texte "
            "(verifie: seule la synthese vocale existe via /v1/speak/higgsfield). "
            "Fournissez un MP3 existant plutot que de demander une composition."
        )
