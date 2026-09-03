from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .audio_analysis import AudioAnalysisUnavailable, analyze_audio_file
from .config import MODES, UPLOAD_DIR
from .director import (
    CAMERA_OPTIONS,
    CHARACTER_OPTIONS,
    DANCE_OPTIONS,
    DECOR_OPTIONS,
    ERA_OPTIONS,
    STYLE_OPTIONS,
    DirectorSettings,
)
from .generators import GenerationError, get_generator
from .models import (
    GeneratedAssetOut,
    GeneratePromptRequest,
    OutputPlanOut,
    SceneOut,
    ShortClipOut,
    StoryboardRequest,
    StoryboardResponse,
    VariantOut,
)
from .outputs_planner import plan_outputs
from .storyboard import build_storyboard

app = FastAPI(title="Music-to-Story Video AI")

_uploads: dict[str, Path] = {}
_static_dir = Path(__file__).resolve().parent.parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/")
def index():
    index_file = _static_dir / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    raise HTTPException(status_code=404, detail="Frontend introuvable")


@app.get("/api/config")
def get_config():
    generator = get_generator()
    return {
        "provider": generator.name,
        "modes": MODES,
        "director_options": {
            "characters": CHARACTER_OPTIONS,
            "style": STYLE_OPTIONS,
            "dance": DANCE_OPTIONS,
            "era": ERA_OPTIONS,
            "decor": DECOR_OPTIONS,
            "camera": CAMERA_OPTIONS,
        },
    }


def _save_upload(upload: UploadFile) -> tuple[str, Path]:
    token = uuid.uuid4().hex
    suffix = Path(upload.filename or "").suffix
    dest = UPLOAD_DIR / f"{token}{suffix}"
    with dest.open("wb") as f:
        shutil.copyfileobj(upload.file, f)
    _uploads[token] = dest
    return token, dest


@app.post("/api/upload/audio")
def upload_audio(file: UploadFile = File(...)):
    token, dest = _save_upload(file)
    audio_summary: Optional[dict] = None
    try:
        features = analyze_audio_file(str(dest))
        audio_summary = {
            "duration": features.duration,
            "tempo_bpm": features.tempo_bpm,
            "suggested_genre_family": features.suggested_genre_family(),
            "segments": [
                {"start": s.start, "end": s.end, "energy": s.energy} for s in features.segments
            ],
        }
    except AudioAnalysisUnavailable as exc:
        audio_summary = {"error": str(exc)}
    return {"token": token, "audio_summary": audio_summary}


@app.post("/api/upload/character")
def upload_character(file: UploadFile = File(...)):
    token, _dest = _save_upload(file)
    return {"token": token, "url": f"/media/{token}"}


@app.get("/media/{token}")
def get_media(token: str):
    path = _uploads.get(token)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    return FileResponse(str(path))


def _audio_features_from_token(token: Optional[str]):
    if not token:
        return None
    path = _uploads.get(token)
    if not path:
        return None
    try:
        return analyze_audio_file(str(path))
    except AudioAnalysisUnavailable:
        return None


@app.post("/api/storyboard", response_model=StoryboardResponse)
def create_storyboard(payload: StoryboardRequest):
    if payload.mode not in MODES:
        raise HTTPException(status_code=400, detail=f"Mode inconnu: {payload.mode}")
    if not payload.lyrics.strip():
        raise HTTPException(status_code=400, detail="Les paroles sont requises pour construire le storyboard.")

    director = DirectorSettings(**payload.director.model_dump())
    audio_features = _audio_features_from_token(payload.audio_token)

    storyboard = build_storyboard(payload.lyrics, director, payload.genre, audio=audio_features)
    output_plan = plan_outputs(storyboard)

    audio_summary = None
    if audio_features:
        audio_summary = {
            "duration": audio_features.duration,
            "tempo_bpm": audio_features.tempo_bpm,
            "suggested_genre_family": audio_features.suggested_genre_family(),
        }

    return StoryboardResponse(
        genre=storyboard.genre,
        overall_mood=storyboard.overall_mood,
        scenes=[SceneOut(**vars(s)) for s in storyboard.scenes],
        output_plan=OutputPlanOut(
            main_clip_scene_indices=output_plan.main_clip_scene_indices,
            shorts=[ShortClipOut(**vars(s)) for s in output_plan.shorts],
            visualizer_mood=output_plan.visualizer_mood,
            lyric_video_scene_indices=output_plan.lyric_video_scene_indices,
            image_scene_indices=output_plan.image_scene_indices,
            variants=[VariantOut(**vars(v)) for v in output_plan.variants],
        ),
        audio_summary=audio_summary,
    )


def _resolve_reference_url(request_base: str, token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    return f"{request_base}/media/{token}"


@app.post("/api/generate/image", response_model=GeneratedAssetOut)
def generate_image(payload: GeneratePromptRequest):
    generator = get_generator()
    try:
        asset = generator.generate_image(payload.prompt, character_reference_url=payload.character_reference_url)
    except GenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return GeneratedAssetOut(kind=asset.kind, url=asset.url, provider=asset.provider, job_id=asset.job_id)


@app.post("/api/generate/video", response_model=GeneratedAssetOut)
def generate_video(payload: GeneratePromptRequest):
    generator = get_generator()
    try:
        asset = generator.generate_video(
            payload.prompt,
            duration_seconds=payload.duration_seconds,
            character_reference_url=payload.character_reference_url,
        )
    except GenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return GeneratedAssetOut(kind=asset.kind, url=asset.url, provider=asset.provider, job_id=asset.job_id)


@app.post("/api/generate/audio", response_model=GeneratedAssetOut)
def generate_audio(payload: GeneratePromptRequest):
    generator = get_generator()
    try:
        asset = generator.generate_audio(payload.prompt, duration_seconds=payload.duration_seconds)
    except GenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return GeneratedAssetOut(kind=asset.kind, url=asset.url, provider=asset.provider, job_id=asset.job_id)
