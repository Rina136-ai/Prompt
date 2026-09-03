from unittest.mock import MagicMock

import pytest

from app.generators.base import GenerationError
from app.generators.higgsfield import HiggsfieldGenerator
from app.generators.mock import MockGenerator


def test_mock_generator_is_deterministic():
    gen = MockGenerator()
    a1 = gen.generate_image("un chat")
    a2 = gen.generate_image("un chat")
    a3 = gen.generate_image("un chien")
    assert a1.url == a2.url
    assert a1.url != a3.url
    assert a1.kind == "image"
    assert a1.provider == "mock"


def _fake_response(json_data, ok=True, status_code=200):
    resp = MagicMock()
    resp.ok = ok
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = str(json_data)
    return resp


def test_higgsfield_generator_requires_api_key():
    with pytest.raises(GenerationError):
        HiggsfieldGenerator(api_key="")


def test_higgsfield_generate_image_happy_path():
    session = MagicMock()
    session.post.return_value = _fake_response({"id": "job-123"})
    session.get.return_value = _fake_response({"status": "succeeded", "output_url": "https://cdn.example/img.png"})

    gen = HiggsfieldGenerator(api_key="secret", session=session, poll_interval_seconds=0)
    asset = gen.generate_image("un danseur afrobeat photorealiste")

    assert asset.url == "https://cdn.example/img.png"
    assert asset.job_id == "job-123"
    assert asset.provider == "higgsfield"
    posted_payload = session.post.call_args.kwargs["json"]
    assert posted_payload["prompt"] == "un danseur afrobeat photorealiste"


def test_higgsfield_generate_image_with_character_reference():
    session = MagicMock()
    session.post.return_value = _fake_response({"id": "job-1"})
    session.get.return_value = _fake_response({"status": "succeeded", "url": "https://cdn.example/img2.png"})

    gen = HiggsfieldGenerator(api_key="secret", session=session, poll_interval_seconds=0)
    gen.generate_image("prompt", character_reference_url="https://cdn.example/ref.png")

    payload = session.post.call_args.kwargs["json"]
    assert payload["reference_image_urls"] == ["https://cdn.example/ref.png"]


def test_higgsfield_raises_on_submit_error():
    session = MagicMock()
    session.post.return_value = _fake_response({"error": "bad request"}, ok=False, status_code=400)

    gen = HiggsfieldGenerator(api_key="secret", session=session, poll_interval_seconds=0)
    with pytest.raises(GenerationError):
        gen.generate_image("x")


def test_higgsfield_raises_on_job_failure():
    session = MagicMock()
    session.post.return_value = _fake_response({"id": "job-9"})
    session.get.return_value = _fake_response({"status": "failed", "error": "content policy"})

    gen = HiggsfieldGenerator(api_key="secret", session=session, poll_interval_seconds=0)
    with pytest.raises(GenerationError):
        gen.generate_image("x")


def test_higgsfield_generate_audio_and_video_build_expected_payloads():
    session = MagicMock()
    session.post.return_value = _fake_response({"id": "job-a"})
    session.get.return_value = _fake_response({"status": "succeeded", "url": "https://cdn.example/a.wav"})

    gen = HiggsfieldGenerator(api_key="secret", session=session, poll_interval_seconds=0)
    audio = gen.generate_audio("une melodie soul", duration_seconds=20)
    assert audio.kind == "audio"
    assert session.post.call_args.kwargs["json"]["duration"] == 20

    session.get.return_value = _fake_response({"status": "succeeded", "url": "https://cdn.example/v.mp4"})
    video = gen.generate_video("une scene", duration_seconds=8)
    assert video.kind == "video"
