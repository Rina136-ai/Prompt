"""End-to-end test of the PRIORITY flow: MP3 only, no lyrics required.

Runs the real pipeline (real audio analysis + real genre classifier +
real ffmpeg assembly) with MockGenerator standing in for the paid image/
video provider, and checks a real, playable MP4 comes out the other end."""
import json
import shutil
import subprocess
import uuid

import pytest

np = pytest.importorskip("numpy")
sf = pytest.importorskip("soundfile")

from app.director import DirectorSettings  # noqa: E402
from app.generators.mock import MockGenerator  # noqa: E402
from app.pipeline import PipelineJob, run_pipeline  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@pytest.fixture
def synthetic_song(tmp_path):
    sr = 22050
    sections = []
    for freq, amp in [(220, 0.08), (440, 0.3), (196, 0.08)]:
        t = np.linspace(0, 6, sr * 6, endpoint=False)
        sections.append((amp * np.sin(2 * np.pi * freq * t)).astype(np.float32))
    y = np.concatenate(sections)
    path = tmp_path / "song.wav"
    sf.write(str(path), y, sr)
    return str(path)


def test_pipeline_produces_a_playable_clip_from_audio_alone_no_lyrics(synthetic_song):
    job = PipelineJob(id=uuid.uuid4().hex)
    run_pipeline(
        job,
        generator=MockGenerator(),
        audio_path=synthetic_song,
        director=DirectorSettings(),
        lyrics_text=None,
        transcribe=False,  # keep the test offline/fast; transcription is tested separately
    )

    assert job.status == "done", job.error
    assert job.is_demo is True
    assert job.storyboard is not None
    assert len(job.storyboard.scenes) >= 1
    assert all(s.lyrics_excerpt == "" for s in job.storyboard.scenes)  # genuinely no lyrics used
    assert job.output_plan is not None
    assert job.result_path

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", job.result_path],
        capture_output=True, text=True,
    )
    data = json.loads(probe.stdout)
    stream_types = {s["codec_type"] for s in data["streams"]}
    assert stream_types == {"video", "audio"}
    assert float(data["format"]["duration"]) == pytest.approx(18.0, abs=1.0)


def test_pipeline_reports_a_clear_error_instead_of_crashing_on_bad_audio(tmp_path):
    bad_file = tmp_path / "not_audio.mp3"
    bad_file.write_bytes(b"this is not an audio file")

    job = PipelineJob(id=uuid.uuid4().hex)
    run_pipeline(job, generator=MockGenerator(), audio_path=str(bad_file), director=DirectorSettings())

    assert job.status == "error"
    assert job.error
