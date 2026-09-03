import json
import shutil
import subprocess

import pytest

from app.character_reference import ensure_provider_reference
from app.generators.mock import MockGenerator
from app.project_dna import CharacterProfile

np = pytest.importorskip("numpy")
sf = pytest.importorskip("soundfile")

from app.video_assembler import extract_audio_segment  # noqa: E402

pytestmark_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def test_multiple_characters_get_distinct_provider_refs():
    gen = MockGenerator()
    principal = CharacterProfile(id="figure_principale", role="narrateur_principal", description="un narrateur solitaire")
    secondaire = CharacterProfile(id="figure_secondaire", role="figure_secondaire", description="un amour evoque")

    ref1 = ensure_provider_reference(gen, principal)
    ref2 = ensure_provider_reference(gen, secondaire)

    assert ref1 != ref2
    assert principal.provider_refs["mock"] == ref1
    assert secondaire.provider_refs["mock"] == ref2


def test_already_resolved_character_is_not_re_resolved(monkeypatch):
    gen = MockGenerator()
    character = CharacterProfile(id="figure_principale", role="narrateur_principal", description="x")

    first = ensure_provider_reference(gen, character)
    assert character.provider_refs["mock"] == first

    calls = {"count": 0}
    original = gen.create_character_reference

    def counting(*args, **kwargs):
        calls["count"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(gen, "create_character_reference", counting)
    second = ensure_provider_reference(gen, character)

    assert second == first
    assert calls["count"] == 0  # cached -- no re-resolution, no re-charge


def test_uploaded_photo_is_used_instead_of_generating_a_portrait():
    gen = MockGenerator()
    character = CharacterProfile(id="figure_principale", role="narrateur_principal", description="x", source_image_path="/tmp/photo.jpg")
    ref = ensure_provider_reference(gen, character)
    assert ref is not None
    assert character.provider_refs["mock"] == ref


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_extract_audio_segment_produces_a_real_shorter_clip(tmp_path):
    sr = 22050
    duration = 20.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    y = (0.1 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    audio_path = str(tmp_path / "song.wav")
    sf.write(audio_path, y, sr)

    out_path = str(tmp_path / "segment.wav")
    extract_audio_segment(audio_path, 5.0, 15.0, out_path)

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", out_path],
        capture_output=True, text=True,
    )
    data = json.loads(probe.stdout)
    assert float(data["format"]["duration"]) == pytest.approx(10.0, abs=0.2)
