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
    assert gen.is_real is False


def test_mock_generator_video_from_image_and_character_reference():
    gen = MockGenerator()
    video = gen.generate_video_from_image("mock://image/abc.png", "danse energique")
    assert video.kind == "video"
    ref_id = gen.create_character_reference("Heroine", ["mock://image/abc.png"])
    assert ref_id.startswith("mock-ref-")


def _fake_response(json_data, ok=True, status_code=200):
    resp = MagicMock()
    resp.ok = ok
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = str(json_data)
    return resp


def test_higgsfield_generator_requires_credentials():
    with pytest.raises(GenerationError):
        HiggsfieldGenerator(key_id="", key_secret="")


def test_higgsfield_uses_verified_auth_header_and_base_url():
    session = MagicMock()
    gen = HiggsfieldGenerator(key_id="KID", key_secret="KSECRET", session=session, poll_interval_seconds=0)
    assert gen.base_url == "https://platform.higgsfield.ai"
    assert gen._headers["Authorization"] == "Key KID:KSECRET"


def test_higgsfield_generate_image_happy_path():
    session = MagicMock()
    session.post.return_value = _fake_response({"request_id": "req-1", "status": "queued"})
    session.get.return_value = _fake_response(
        {"status": "completed", "request_id": "req-1", "images": [{"url": "https://cdn.example/img.png"}]}
    )

    gen = HiggsfieldGenerator(key_id="KID", key_secret="SEC", session=session, poll_interval_seconds=0)
    asset = gen.generate_image("un danseur afrobeat photorealiste")

    assert asset.url == "https://cdn.example/img.png"
    assert asset.provider == "higgsfield"
    posted_body = session.post.call_args.kwargs["json"]
    assert posted_body["prompt"] == "un danseur afrobeat photorealiste"
    posted_path = session.post.call_args.args[0]
    assert posted_path.endswith("/v1/text2image/soul")


def test_higgsfield_generate_image_with_character_reference_id():
    session = MagicMock()
    session.post.return_value = _fake_response({"request_id": "req-2"})
    session.get.return_value = _fake_response(
        {"status": "completed", "images": [{"url": "https://cdn.example/img2.png"}]}
    )

    gen = HiggsfieldGenerator(key_id="KID", key_secret="SEC", session=session, poll_interval_seconds=0)
    gen.generate_image("prompt", character_reference_id="soul-123")

    payload = session.post.call_args.kwargs["json"]
    assert payload["custom_reference_id"] == "soul-123"


def test_higgsfield_generate_video_from_image_posts_to_dop_endpoint():
    session = MagicMock()
    session.post.return_value = _fake_response({"request_id": "req-3"})
    session.get.return_value = _fake_response({"status": "completed", "video": {"url": "https://cdn.example/v.mp4"}})

    gen = HiggsfieldGenerator(key_id="KID", key_secret="SEC", session=session, poll_interval_seconds=0)
    asset = gen.generate_video_from_image("https://cdn.example/img.png", "mouvement de camera cinematographique")

    assert asset.kind == "video"
    assert asset.url == "https://cdn.example/v.mp4"
    posted_path = session.post.call_args.args[0]
    assert posted_path.endswith("/v1/image2video/dop")
    payload = session.post.call_args.kwargs["json"]
    assert payload["input_images"] == [{"type": "image_url", "image_url": "https://cdn.example/img.png"}]


def test_higgsfield_raises_on_submit_error():
    session = MagicMock()
    session.post.return_value = _fake_response({"detail": "bad request"}, ok=False, status_code=400)

    gen = HiggsfieldGenerator(key_id="KID", key_secret="SEC", session=session, poll_interval_seconds=0)
    with pytest.raises(GenerationError):
        gen.generate_image("x")


def test_higgsfield_raises_401_as_clear_auth_error():
    session = MagicMock()
    session.post.return_value = _fake_response({}, ok=False, status_code=401)
    gen = HiggsfieldGenerator(key_id="KID", key_secret="SEC", session=session, poll_interval_seconds=0)
    with pytest.raises(GenerationError, match="Identifiants Higgsfield invalides"):
        gen.generate_image("x")


def test_higgsfield_raises_on_job_failure():
    session = MagicMock()
    session.post.return_value = _fake_response({"request_id": "req-9"})
    session.get.return_value = _fake_response({"status": "failed"})

    gen = HiggsfieldGenerator(key_id="KID", key_secret="SEC", session=session, poll_interval_seconds=0)
    with pytest.raises(GenerationError):
        gen.generate_image("x")


def test_higgsfield_raises_on_nsfw():
    session = MagicMock()
    session.post.return_value = _fake_response({"request_id": "req-10"})
    session.get.return_value = _fake_response({"status": "nsfw"})

    gen = HiggsfieldGenerator(key_id="KID", key_secret="SEC", session=session, poll_interval_seconds=0)
    with pytest.raises(GenerationError, match="moderation"):
        gen.generate_image("x")


def test_higgsfield_generate_audio_is_explicitly_unsupported():
    session = MagicMock()
    gen = HiggsfieldGenerator(key_id="KID", key_secret="SEC", session=session, poll_interval_seconds=0)
    with pytest.raises(GenerationError, match="musique"):
        gen.generate_audio("une melodie")


def test_higgsfield_create_character_reference_polls_until_completed():
    session = MagicMock()
    session.post.return_value = _fake_response({"id": "soul-1"})
    session.get.side_effect = [
        _fake_response({"status": "in_progress"}),
        _fake_response({"status": "completed"}),
    ]
    gen = HiggsfieldGenerator(key_id="KID", key_secret="SEC", session=session, poll_interval_seconds=0)
    ref_id = gen.create_character_reference("Heroine", ["https://cdn.example/ref.jpg"])
    assert ref_id == "soul-1"
    assert session.get.call_count == 2


def test_higgsfield_upload_file_puts_bytes_to_upload_url(tmp_path):
    local_file = tmp_path / "photo.jpg"
    local_file.write_bytes(b"fake-jpeg-bytes")

    session = MagicMock()
    session.post.return_value = _fake_response(
        {"upload_url": "https://cdn.example/upload/xyz", "public_url": "https://cdn.example/public/xyz.jpg"}
    )
    session.put.return_value = _fake_response({}, ok=True)

    gen = HiggsfieldGenerator(key_id="KID", key_secret="SEC", session=session, poll_interval_seconds=0)
    public_url = gen.upload_file(str(local_file), "image/jpeg")

    assert public_url == "https://cdn.example/public/xyz.jpg"
    session.put.assert_called_once()
