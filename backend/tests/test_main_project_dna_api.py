"""Full HTTP-level test of the new chain: musique -> Project DNA ->
storyboard -> preview (20-30s) -> full clip reusing the same project_id."""
import io
import shutil
import time

import pytest

np = pytest.importorskip("numpy")
sf = pytest.importorskip("soundfile")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

client = TestClient(app)


def _synthetic_song_bytes(sr=22050):
    sections = []
    for freq, amp, dur in [(220, 0.08, 8), (440, 0.3, 8), (196, 0.08, 8), (440, 0.3, 8), (220, 0.08, 8)]:
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        sections.append((amp * np.sin(2 * np.pi * freq * t)).astype(np.float32))
    y = np.concatenate(sections)
    buf = io.BytesIO()
    sf.write(buf, y, sr, format="WAV")
    buf.seek(0)
    return buf


def _poll_until_terminal(url, timeout=90):
    deadline = time.time() + timeout
    data = None
    while time.time() < deadline:
        response = client.get(url)
        assert response.status_code == 200
        data = response.json()
        if data["status"] in ("ready", "error"):
            return data
        time.sleep(0.5)
    raise TimeoutError(f"{url} did not reach a terminal status in time: {data}")


def test_analyze_then_preview_then_full_reuse_the_same_project():
    wav = _synthetic_song_bytes()
    response = client.post("/api/pipeline/analyze", files={"audio": ("song.wav", wav, "audio/wav")})
    assert response.status_code == 200
    project_id = response.json()["project_id"]

    status = _poll_until_terminal(f"/api/pipeline/project/{project_id}")
    assert status["status"] == "ready", status
    assert status["dna"] is not None
    assert status["dna"]["characters"]  # at least the principal character
    assert status["scenes"]  # narrative scenes, not raw sections
    assert status["total_shots"] >= 1

    preview_response = client.post(f"/api/pipeline/preview/{project_id}")
    assert preview_response.status_code == 200
    assert preview_response.json()["is_demo"] is True

    preview_status = _poll_until_terminal(f"/api/pipeline/project/{project_id}")
    assert preview_status["status"] == "ready", preview_status
    assert "preview" in preview_status["outputs_ready"]

    preview_video = client.get(f"/api/pipeline/output/{project_id}/preview")
    assert preview_video.status_code == 200
    assert preview_video.headers["content-type"] == "video/mp4"

    full_response = client.post(f"/api/pipeline/full/{project_id}")
    assert full_response.status_code == 200

    full_status = _poll_until_terminal(f"/api/pipeline/project/{project_id}")
    assert full_status["status"] == "ready", full_status
    assert "full" in full_status["outputs_ready"]

    full_video = client.get(f"/api/pipeline/output/{project_id}/full")
    assert full_video.status_code == 200
    assert len(full_video.content) > len(preview_video.content)


def test_preview_before_analyze_returns_a_clear_conflict():
    response = client.post("/api/pipeline/preview/does-not-exist")
    assert response.status_code == 404


def test_existing_run_endpoint_still_works_unaffected():
    wav = _synthetic_song_bytes()
    response = client.post("/api/pipeline/run", files={"audio": ("song.wav", wav, "audio/wav")})
    assert response.status_code == 200
    assert "job_id" in response.json()
