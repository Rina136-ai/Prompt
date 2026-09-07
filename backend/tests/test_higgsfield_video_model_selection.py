"""Regression tests for the DoP video-model tier selection added when the
Higgsfield contract was re-verified directly against the official
@higgsfield/client npm package source (v0.2.1) ahead of the first real
generation. No live network call: HiggsfieldGenerator is exercised with an
injected mock `requests.Session`, exactly like the rest of test_generators.py.
"""
from unittest.mock import MagicMock

import pytest

from app.generators import DEFAULT_VIDEO_MODEL, get_generator
from app.generators.base import GenerationError
from app.generators.higgsfield import (
    VALID_VIDEO_MODELS,
    VIDEO_MODEL_LITE,
    VIDEO_MODEL_STANDARD,
    VIDEO_MODEL_TURBO,
    HiggsfieldGenerator,
)
from app.generators.mock import MockGenerator


def _fake_response(json_data, ok=True, status_code=200):
    resp = MagicMock()
    resp.ok = ok
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = str(json_data)
    return resp


def test_default_video_model_is_the_cheapest_tier():
    # "Le plus approprie, pas le plus couteux" for a first real test.
    assert DEFAULT_VIDEO_MODEL == VIDEO_MODEL_LITE == "dop-lite"
    assert VALID_VIDEO_MODELS == {"dop-lite", "dop-turbo", "dop-standard"}


def test_generate_video_from_image_uses_the_configured_tier_by_default():
    session = MagicMock()
    session.post.return_value = _fake_response({"request_id": "req-1"})
    session.get.return_value = _fake_response({"status": "completed", "video": {"url": "https://cdn.example/v.mp4"}})

    gen = HiggsfieldGenerator(key_id="KID", key_secret="SEC", session=session, poll_interval_seconds=0)
    gen.generate_video_from_image("https://cdn.example/img.png", "mouvement de camera")

    payload = session.post.call_args.kwargs["json"]
    assert payload["model"] == VIDEO_MODEL_LITE


@pytest.mark.parametrize("tier", [VIDEO_MODEL_LITE, VIDEO_MODEL_TURBO, VIDEO_MODEL_STANDARD])
def test_generate_video_from_image_honors_an_explicit_tier(tier):
    session = MagicMock()
    session.post.return_value = _fake_response({"request_id": "req-1"})
    session.get.return_value = _fake_response({"status": "completed", "video": {"url": "https://cdn.example/v.mp4"}})

    gen = HiggsfieldGenerator(key_id="KID", key_secret="SEC", session=session, video_model=tier, poll_interval_seconds=0)
    gen.generate_video_from_image("https://cdn.example/img.png", "mouvement de camera")

    payload = session.post.call_args.kwargs["json"]
    assert payload["model"] == tier


def test_unknown_video_model_tier_is_rejected_immediately_not_at_call_time():
    with pytest.raises(GenerationError, match="Modele video DoP inconnu"):
        HiggsfieldGenerator(key_id="KID", key_secret="SEC", video_model="dop-ultra-does-not-exist")


def test_get_generator_reads_video_model_tier_from_env(monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_KEY_ID", "KID")
    monkeypatch.setenv("HIGGSFIELD_KEY_SECRET", "SEC")
    monkeypatch.setenv("HIGGSFIELD_VIDEO_MODEL", VIDEO_MODEL_STANDARD)

    generator = get_generator()

    assert isinstance(generator, HiggsfieldGenerator)
    assert generator.video_model == VIDEO_MODEL_STANDARD


def test_get_generator_defaults_to_lite_tier_when_env_var_absent(monkeypatch):
    monkeypatch.setenv("HIGGSFIELD_KEY_ID", "KID")
    monkeypatch.setenv("HIGGSFIELD_KEY_SECRET", "SEC")
    monkeypatch.delenv("HIGGSFIELD_VIDEO_MODEL", raising=False)

    generator = get_generator()

    assert isinstance(generator, HiggsfieldGenerator)
    assert generator.video_model == VIDEO_MODEL_LITE


def test_get_generator_without_credentials_still_returns_the_mock(monkeypatch):
    monkeypatch.delenv("HIGGSFIELD_KEY_ID", raising=False)
    monkeypatch.delenv("HIGGSFIELD_KEY_SECRET", raising=False)
    monkeypatch.delenv("HIGGSFIELD_CREDENTIALS", raising=False)

    assert isinstance(get_generator(), MockGenerator)


def test_character_reference_mechanism_is_untouched_and_stays_instant_single_image():
    # Explicitly guards against silently swapping in an unverified "Reference
    # Elements" endpoint: /v1/custom-references must still accept a single
    # image, no training step, exactly as before.
    session = MagicMock()
    session.post.return_value = _fake_response({"id": "soul-1"})
    session.get.return_value = _fake_response({"status": "completed"})

    gen = HiggsfieldGenerator(key_id="KID", key_secret="SEC", session=session, poll_interval_seconds=0)
    ref_id = gen.create_character_reference("Personnage principal", ["https://cdn.example/ref.jpg"])

    assert ref_id == "soul-1"
    posted_path = session.post.call_args.args[0]
    assert posted_path.endswith("/v1/custom-references")
    posted_body = session.post.call_args.kwargs["json"]
    assert posted_body["input_images"] == [{"type": "image_url", "image_url": "https://cdn.example/ref.jpg"}]
