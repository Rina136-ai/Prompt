"""Real ffmpeg integration test: builds an actual final MP4 from mock scene
assets and a synthetic audio track, then inspects the real output file with
ffprobe. Skipped if ffmpeg/ffprobe aren't on PATH."""
import json
import shutil
import subprocess

import pytest

np = pytest.importorskip("numpy")
sf = pytest.importorskip("soundfile")

from app.generators.base import GeneratedAsset  # noqa: E402
from app.video_assembler import (  # noqa: E402
    concat_clips,
    download_asset,
    fit_clip_to_duration,
    mux_with_audio,
)

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed",
)


def _ffprobe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", path],
        capture_output=True, text=True,
    )
    return json.loads(out.stdout)


@pytest.fixture
def synthetic_audio(tmp_path):
    sr = 22050
    duration = 9.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    y = (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    path = tmp_path / "song.wav"
    sf.write(str(path), y, sr)
    return str(path)


def test_full_assembly_produces_a_real_playable_mp4_with_audio(tmp_path, synthetic_audio):
    work_dir = str(tmp_path / "job")
    mock_assets = [GeneratedAsset(kind="video", url=f"mock://video/scene{i}.mp4", provider="mock") for i in range(3)]

    downloaded = [download_asset(asset, work_dir, f"scene_{i:02d}") for i, asset in enumerate(mock_assets)]
    section_durations = [3.0, 3.0, 3.0]
    fitted = [
        fit_clip_to_duration(path, dur, f"{work_dir}/fit_{i:02d}.mp4")
        for i, (path, dur) in enumerate(zip(downloaded, section_durations))
    ]
    concatenated = concat_clips(fitted, f"{work_dir}/concatenated.mp4")
    final_path = mux_with_audio(concatenated, synthetic_audio, f"{work_dir}/final.mp4")

    probe = _ffprobe(final_path)
    stream_types = {s["codec_type"] for s in probe["streams"]}
    assert stream_types == {"video", "audio"}
    assert float(probe["format"]["duration"]) == pytest.approx(9.0, abs=0.5)
