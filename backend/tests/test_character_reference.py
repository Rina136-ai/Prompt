from unittest.mock import MagicMock

from app.character_reference import ensure_character_reference
from app.director import DirectorSettings
from app.generators.base import GenerationError
from app.generators.mock import MockGenerator


def test_mock_generator_auto_generates_a_reference_portrait_when_no_photo_given():
    gen = MockGenerator()
    ref_id = ensure_character_reference(gen, DirectorSettings())
    assert ref_id is not None
    assert ref_id.startswith("mock-ref-")


def test_uploads_provided_photo_instead_of_generating_a_portrait(tmp_path):
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"fake-jpeg")
    gen = MagicMock()
    gen.upload_file.return_value = "https://cdn.example/uploaded.jpg"
    gen.create_character_reference.return_value = "soul-42"

    ref_id = ensure_character_reference(gen, DirectorSettings(), uploaded_photo_path=str(photo))

    assert ref_id == "soul-42"
    gen.upload_file.assert_called_once_with(str(photo), "image/jpeg")
    gen.generate_image.assert_not_called()
    gen.create_character_reference.assert_called_once_with("Personnage principal", ["https://cdn.example/uploaded.jpg"])


def test_generates_a_portrait_prompt_mentioning_director_settings_when_no_photo():
    gen = MagicMock()
    gen.generate_image.return_value.url = "https://cdn.example/portrait.png"
    gen.create_character_reference.return_value = "soul-1"

    director = DirectorSettings(characters="africains", style="photorealiste")
    ensure_character_reference(gen, director)

    prompt = gen.generate_image.call_args.args[0]
    assert "africains" in prompt
    assert "photorealiste" in prompt


def test_returns_none_when_provider_refuses_gracefully_instead_of_raising():
    gen = MagicMock()
    gen.generate_image.side_effect = GenerationError("credits insuffisants")

    ref_id = ensure_character_reference(gen, DirectorSettings())

    assert ref_id is None
