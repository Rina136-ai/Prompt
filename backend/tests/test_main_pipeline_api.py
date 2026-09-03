"""Full-stack test of the priority flow through the real HTTP API: upload an
MP3-like file with NOTHING else set, poll status, download the real MP4."""
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


def _synthetic_wav_bytes(duration=15.0, sr=22050):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    y = (0.15 * np.sin(2 * np.pi * 330 * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, y, sr, format="WAV")
    buf.seek(0)
    return buf


def test_config_endpoint_reports_demo_mode_without_credentials():
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "mock"
    assert data["is_demo"] is True


def test_pipeline_run_with_mp3_only_no_lyrics_no_director_settings():
    wav = _synthetic_wav_bytes()
    response = client.post(
        "/api/pipeline/run",
        files={"audio": ("song.wav", wav, "audio/wav")},
    )
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    deadline = time.time() + 60
    status_data = None
    while time.time() < deadline:
        status_response = client.get(f"/api/pipeline/status/{job_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()
        if status_data["status"] in ("done", "error"):
            break
        time.sleep(0.5)

    assert status_data["status"] == "done", status_data
    assert status_data["is_demo"] is True
    assert status_data["result_ready"] is True
    assert status_data["storyboard"] is not None
    assert len(status_data["storyboard"]["scenes"]) >= 1

    result_response = client.get(f"/api/pipeline/result/{job_id}")
    assert result_response.status_code == 200
    assert result_response.headers["content-type"] == "video/mp4"
    assert len(result_response.content) > 1000
