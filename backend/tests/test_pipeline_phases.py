"""Phase A (free) / Phase B (only phase that calls the generator) with
MockGenerator: proves the chain musique -> Project DNA -> storyboard ->
shots -> generation -> assembly, and that a full clip requested after a
preview does not regenerate/re-bill shots already rendered."""
import json
import shutil
import subprocess
import uuid

import pytest

np = pytest.importorskip("numpy")
sf = pytest.importorskip("soundfile")

from app.director import DirectorSettings  # noqa: E402
from app.generators.mock import MockGenerator  # noqa: E402
from app.outputs_planner import plan_preview  # noqa: E402
from app.pipeline import RenderProject, build_project, render_shots  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@pytest.fixture
def synthetic_song(tmp_path):
    sr = 22050
    sections = []
    for freq, amp, dur in [(220, 0.08, 8), (440, 0.3, 8), (196, 0.08, 8), (440, 0.3, 8), (220, 0.08, 8)]:
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        sections.append((amp * np.sin(2 * np.pi * freq * t)).astype(np.float32))
    y = np.concatenate(sections)
    path = tmp_path / "song.wav"
    sf.write(str(path), y, sr)
    return str(path)


def _ffprobe_duration(path):
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
        capture_output=True, text=True,
    )
    return float(json.loads(probe.stdout)["format"]["duration"])


def test_build_project_never_touches_the_generator(synthetic_song):
    project = RenderProject(id=uuid.uuid4().hex)
    build_project(project, synthetic_song, DirectorSettings())

    assert project.status == "ready", project.error
    assert project.dna is not None
    assert project.storyboard is not None
    assert len(project.storyboard.all_shots()) >= 1
    assert project.rendered_shots == {}  # Phase A generated nothing


def test_preview_then_full_reuses_already_rendered_shots(synthetic_song):
    project = RenderProject(id=uuid.uuid4().hex)
    build_project(project, synthetic_song, DirectorSettings(), transcribe=False)
    assert project.status == "ready", project.error

    generator = MockGenerator()

    preview_plan = plan_preview(project.storyboard)
    assert preview_plan.shot_indices, "the synthetic song should yield at least one previewable shot"

    preview_path = render_shots(project, generator, preview_plan.shot_indices, output_name="preview")
    assert preview_path, project.error
    rendered_after_preview = set(project.rendered_shots.keys())
    assert set(preview_plan.shot_indices) <= rendered_after_preview

    all_shot_indices = [shot.index for shot in project.storyboard.all_shots()]

    class CountingGenerator(MockGenerator):
        def __init__(self):
            super().__init__()
            self.image_calls = 0
            self.video_calls = 0

        def generate_image(self, *args, **kwargs):
            self.image_calls += 1
            return super().generate_image(*args, **kwargs)

        def generate_video_from_image(self, *args, **kwargs):
            self.video_calls += 1
            return super().generate_video_from_image(*args, **kwargs)

    counting_generator = CountingGenerator()
    # Re-attach the same rendered_shots cache to prove the dedup, using the same project.
    full_path = render_shots(project, counting_generator, all_shot_indices, output_name="full")
    assert full_path, project.error

    expected_new_calls = len(all_shot_indices) - len(rendered_after_preview & set(all_shot_indices))
    assert counting_generator.image_calls == expected_new_calls
    assert counting_generator.video_calls == expected_new_calls

    preview_duration = _ffprobe_duration(preview_path)
    full_duration = _ffprobe_duration(full_path)
    assert preview_duration < full_duration
    assert full_duration == pytest.approx(project.dna.duration_seconds, abs=0.5)


def test_render_shots_before_build_project_fails_clearly():
    project = RenderProject(id=uuid.uuid4().hex)
    result = render_shots(project, MockGenerator(), [0], output_name="x")
    assert result is None
    assert project.status == "error"
    assert "analyse" in project.error.lower()
