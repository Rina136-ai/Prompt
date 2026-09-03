from __future__ import annotations

import shutil
import threading
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .audio_analysis import AudioAnalysisUnavailable, analyze_audio_file
from .character_reference import ensure_character_reference
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
    AnalyzeStartResponse,
    CharacterProfileOut,
    DirectorSettingsIn,
    GenerateAudioRequest,
    GenerateImageRequest,
    GeneratedAssetOut,
    GenerateVideoFromImageRequest,
    NarrativeSceneOut,
    OutputPlanOut,
    PipelineStartResponse,
    PipelineStatusResponse,
    ProjectDNAOut,
    ProjectStatusResponse,
    RenderStartResponse,
    SceneOut,
    ShortClipOut,
    StoryboardRequest,
    StoryboardResponse,
    VariantOut,
)
from .outputs_planner import OutputPlan, plan_outputs, plan_preview
from .pipeline import PipelineJob, RenderProject, build_project, render_shots, run_pipeline
from .storyboard import Storyboard, build_storyboard

app = FastAPI(title="Music-to-Story Video AI")

_uploads: dict[str, Path] = {}
_jobs: dict[str, PipelineJob] = {}
_projects: dict[str, RenderProject] = {}
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
        "is_demo": not generator.is_real,
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
            "sections": [
                {"start": s.start, "end": s.end, "energy": s.energy, "local_tempo_bpm": s.local_tempo_bpm}
                for s in features.sections
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


def _storyboard_response(storyboard: Storyboard, output_plan: OutputPlan, audio_summary: Optional[dict]) -> StoryboardResponse:
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


@app.post("/api/storyboard", response_model=StoryboardResponse)
def create_storyboard(payload: StoryboardRequest):
    """Advanced/manual storyboard endpoint (lyrics required). For the simple
    "MP3 seul" priority flow with no lyrics, use /api/pipeline/run instead."""
    if payload.mode not in MODES:
        raise HTTPException(status_code=400, detail=f"Mode inconnu: {payload.mode}")
    if not payload.lyrics.strip():
        raise HTTPException(
            status_code=400,
            detail="Les paroles sont requises pour ce endpoint manuel. Pour generer un clip a partir d'un MP3 seul, utilisez /api/pipeline/run.",
        )

    director = DirectorSettings(**payload.director.model_dump(exclude={"character_reference_media_id"}))
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

    return _storyboard_response(storyboard, output_plan, audio_summary)


@app.post("/api/character-reference")
def create_character_reference_endpoint(photo_token: Optional[str] = Form(None), director: str = Form("{}")):
    import json

    generator = get_generator()
    director_settings = DirectorSettings(**DirectorSettingsIn(**json.loads(director)).model_dump(exclude={"character_reference_media_id"}))
    photo_path = str(_uploads[photo_token]) if photo_token and photo_token in _uploads else None
    reference_id = ensure_character_reference(generator, director_settings, uploaded_photo_path=photo_path)
    if reference_id is None:
        raise HTTPException(status_code=502, detail="Impossible de creer un personnage de reference avec ce fournisseur.")
    return {"character_reference_id": reference_id, "provider": generator.name, "is_demo": not generator.is_real}


@app.post("/api/generate/image", response_model=GeneratedAssetOut)
def generate_image(payload: GenerateImageRequest):
    generator = get_generator()
    try:
        asset = generator.generate_image(payload.prompt, character_reference_id=payload.character_reference_id)
    except GenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return GeneratedAssetOut(kind=asset.kind, url=asset.url, provider=asset.provider, job_id=asset.job_id)


@app.post("/api/generate/video", response_model=GeneratedAssetOut)
def generate_video(payload: GenerateVideoFromImageRequest):
    """Image-to-video: Higgsfield (like most real providers) animates an
    existing image rather than generating video from text alone, so a scene
    image must be generated first via /api/generate/image."""
    generator = get_generator()
    try:
        asset = generator.generate_video_from_image(payload.image_url, payload.prompt, motion_hint=payload.motion_hint)
    except GenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return GeneratedAssetOut(kind=asset.kind, url=asset.url, provider=asset.provider, job_id=asset.job_id)


@app.post("/api/generate/audio", response_model=GeneratedAssetOut)
def generate_audio(payload: GenerateAudioRequest):
    generator = get_generator()
    try:
        asset = generator.generate_audio(payload.prompt, duration_seconds=payload.duration_seconds)
    except GenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return GeneratedAssetOut(kind=asset.kind, url=asset.url, provider=asset.provider, job_id=asset.job_id)


# ---------------------------------------------------------------------------
# Priority flow: "Importer ma musique -> Analyser -> Generer mon clip ->
# Regarder/Telecharger". Lyrics, character photo and director settings are
# all optional -- an MP3 alone is enough to produce a full clip.
# ---------------------------------------------------------------------------


@app.post("/api/pipeline/run", response_model=PipelineStartResponse)
def start_pipeline(
    audio: UploadFile = File(...),
    lyrics: Optional[str] = Form(None),
    genre: Optional[str] = Form(None),
    director: str = Form("{}"),
    character_photo: Optional[UploadFile] = File(None),
):
    import json

    _token, audio_path = _save_upload(audio)
    character_photo_path: Optional[str] = None
    if character_photo is not None:
        _ctoken, character_photo_path_obj = _save_upload(character_photo)
        character_photo_path = str(character_photo_path_obj)

    director_settings = DirectorSettings(**DirectorSettingsIn(**json.loads(director)).model_dump(exclude={"character_reference_media_id"}))

    job = PipelineJob(id=uuid.uuid4().hex)
    _jobs[job.id] = job

    generator = get_generator()
    thread = threading.Thread(
        target=run_pipeline,
        kwargs=dict(
            job=job,
            generator=generator,
            audio_path=str(audio_path),
            director=director_settings,
            lyrics_text=lyrics or None,
            character_photo_path=character_photo_path,
            genre_override=genre or None,
        ),
        daemon=True,
    )
    thread.start()

    return PipelineStartResponse(job_id=job.id)


@app.get("/api/pipeline/status/{job_id}", response_model=PipelineStatusResponse)
def get_pipeline_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job introuvable")

    storyboard_response = None
    if job.storyboard is not None and job.output_plan is not None:
        storyboard_response = _storyboard_response(job.storyboard, job.output_plan, audio_summary=None)

    return PipelineStatusResponse(
        job_id=job.id,
        status=job.status,
        progress=job.progress,
        error=job.error,
        provider=job.provider,
        is_demo=job.is_demo,
        genre_detected=job.genre_detected,
        storyboard=storyboard_response,
        result_ready=job.status == "done" and bool(job.result_path),
    )


@app.get("/api/pipeline/result/{job_id}")
def get_pipeline_result(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job introuvable")
    if job.status != "done" or not job.result_path:
        raise HTTPException(status_code=409, detail=f"Le clip n'est pas encore pret (statut: {job.status}).")
    filename = "clip_demo.mp4" if job.is_demo else "clip.mp4"
    return FileResponse(job.result_path, media_type="video/mp4", filename=filename)


# ---------------------------------------------------------------------------
# Project DNA flow: musique -> comprehension globale -> scenes -> plans.
#
# Phase A (/analyze) never calls a Generator method -- it's free to run and
# inspect. Phase B (/preview, /full) is the only phase that spends credits;
# /full reuses the exact same project_id/DNA/storyboard/characters and never
# re-renders a shot already produced by /preview. Everything above this
# point (/api/pipeline/run and friends) is untouched for backward
# compatibility.
# ---------------------------------------------------------------------------


@app.post("/api/pipeline/analyze", response_model=AnalyzeStartResponse)
def start_analyze(
    audio: UploadFile = File(...),
    lyrics: Optional[str] = Form(None),
    genre: Optional[str] = Form(None),
    director: str = Form("{}"),
    character_photo: Optional[UploadFile] = File(None),
):
    import json

    _token, audio_path = _save_upload(audio)
    character_photo_path: Optional[str] = None
    if character_photo is not None:
        _ctoken, character_photo_path_obj = _save_upload(character_photo)
        character_photo_path = str(character_photo_path_obj)

    director_settings = DirectorSettings(
        **DirectorSettingsIn(**json.loads(director)).model_dump(exclude={"character_reference_media_id"})
    )

    project = RenderProject(id=uuid.uuid4().hex)
    _projects[project.id] = project

    thread = threading.Thread(
        target=build_project,
        kwargs=dict(
            project=project,
            audio_path=str(audio_path),
            director=director_settings,
            lyrics_text=lyrics or None,
            character_photo_path=character_photo_path,
            genre_override=genre or None,
        ),
        daemon=True,
    )
    thread.start()

    return AnalyzeStartResponse(project_id=project.id)


def _project_status_response(project: RenderProject) -> ProjectStatusResponse:
    dna_out = None
    scenes_out = None
    total_shots = None

    if project.dna is not None:
        dna_out = ProjectDNAOut(
            genre=project.dna.genre,
            duration_seconds=project.dna.duration_seconds,
            tempo_bpm=project.dna.tempo_bpm,
            synopsis=project.dna.narrative.synopsis,
            characters=[
                CharacterProfileOut(id=c.id, role=c.role, description=c.description, has_photo=bool(c.source_image_path))
                for c in project.dna.characters
            ],
            referenced_presences_count=len(project.dna.referenced_presences),
        )

    if project.storyboard is not None:
        scenes_out = [
            NarrativeSceneOut(
                index=s.index,
                role=s.role,
                start_seconds=s.start_seconds,
                end_seconds=s.end_seconds,
                energy=s.energy,
                mood=s.mood,
                is_chorus_scene=s.is_chorus_scene,
                shot_count=len(s.shots),
            )
            for s in project.storyboard.scenes
        ]
        total_shots = len(project.storyboard.all_shots())

    return ProjectStatusResponse(
        project_id=project.id,
        status=project.status,
        progress=project.progress,
        error=project.error,
        genre_detected=project.genre_detected,
        dna=dna_out,
        scenes=scenes_out,
        total_shots=total_shots,
        outputs_ready=list(project.outputs.keys()),
    )


@app.get("/api/pipeline/project/{project_id}", response_model=ProjectStatusResponse)
def get_project_status(project_id: str):
    project = _projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    return _project_status_response(project)


@app.post("/api/pipeline/preview/{project_id}", response_model=RenderStartResponse)
def start_preview(project_id: str):
    project = _projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    if project.storyboard is None:
        raise HTTPException(status_code=409, detail=f"Le projet n'est pas encore analyse (statut: {project.status}).")

    preview_plan = plan_preview(project.storyboard)
    generator = get_generator()

    thread = threading.Thread(
        target=render_shots,
        kwargs=dict(project=project, generator=generator, shot_indices=preview_plan.shot_indices, output_name="preview"),
        daemon=True,
    )
    thread.start()

    return RenderStartResponse(project_id=project.id, output_name="preview", is_demo=not generator.is_real, provider=generator.name)


@app.post("/api/pipeline/full/{project_id}", response_model=RenderStartResponse)
def start_full(project_id: str):
    """Renders every shot of the storyboard against the SAME project_id used
    for /preview -- shots already rendered there are reused, never re-billed."""
    project = _projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    if project.storyboard is None:
        raise HTTPException(status_code=409, detail=f"Le projet n'est pas encore analyse (statut: {project.status}).")

    all_shot_indices = [shot.index for shot in project.storyboard.all_shots()]
    generator = get_generator()

    thread = threading.Thread(
        target=render_shots,
        kwargs=dict(project=project, generator=generator, shot_indices=all_shot_indices, output_name="full"),
        daemon=True,
    )
    thread.start()

    return RenderStartResponse(project_id=project.id, output_name="full", is_demo=not generator.is_real, provider=generator.name)


@app.get("/api/pipeline/output/{project_id}/{output_name}")
def get_project_output(project_id: str, output_name: str):
    project = _projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    path = project.outputs.get(output_name)
    if not path:
        raise HTTPException(status_code=409, detail=f"'{output_name}' n'est pas encore pret (statut: {project.status}).")
    is_demo = not get_generator().is_real
    filename = f"{output_name}_demo.mp4" if is_demo else f"{output_name}.mp4"
    return FileResponse(path, media_type="video/mp4", filename=filename)
