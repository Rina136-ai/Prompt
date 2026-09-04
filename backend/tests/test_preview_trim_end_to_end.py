"""End-to-end (real ffmpeg, MockGenerator) proof that a trimmed preview
plan actually produces a shorter rendered file than the shot's natural
duration would -- not just a planning-level number."""
import json
import shutil
import subprocess
import uuid

import pytest

np = pytest.importorskip("numpy")
sf = pytest.importorskip("soundfile")

from app.director import DirectorSettings  # noqa: E402
from app.generators.mock import MockGenerator  # noqa: E402
from app.pipeline import RenderProject, build_project, render_shots  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _ffprobe_duration(path):
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
        capture_output=True, text=True,
    )
    return float(json.loads(probe.stdout)["format"]["duration"])


def test_shot_duration_override_shortens_the_rendered_output(tmp_path):
    sr = 22050
    duration = 20.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    y = (0.1 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    audio_path = str(tmp_path / "song.wav")
    sf.write(audio_path, y, sr)

    project = RenderProject(id=uuid.uuid4().hex)
    build_project(project, audio_path, DirectorSettings(), transcribe=False)
    assert project.status == "ready", project.error

    all_shots = project.storyboard.all_shots()
    first_shot = all_shots[0]
    natural_duration = first_shot.end_seconds - first_shot.start_seconds
    shortened = round(natural_duration / 2, 2)

    path_untrimmed = render_shots(project, MockGenerator(), [first_shot.index], output_name="untrimmed")
    assert path_untrimmed, project.error

    path_trimmed = render_shots(
        project, MockGenerator(), [first_shot.index], output_name="trimmed",
        shot_duration_overrides={first_shot.index: shortened},
    )
    assert path_trimmed, project.error

    duration_untrimmed = _ffprobe_duration(path_untrimmed)
    duration_trimmed = _ffprobe_duration(path_trimmed)

    assert duration_trimmed < duration_untrimmed
    assert duration_trimmed == pytest.approx(shortened, abs=0.5)
