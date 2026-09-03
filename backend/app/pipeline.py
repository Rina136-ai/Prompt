"""End-to-end pipeline: an uploaded MP3 (lyrics/photo/director settings all
optional) -> real analysis -> storyboard -> generation -> assembled MP4.

This is what powers the simple "Importer -> Analyser -> Generer ->
Regarder/Telecharger" flow. It runs as a background job (see main.py)
because real generation of several scenes can take many minutes.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import video_assembler
from .audio_analysis import analyze_audio_file
from .character_reference import ensure_character_reference
from .director import DirectorSettings
from .generators.base import GenerationError, Generator
from .genre_classifier import GenreClassificationUnavailable, classify_genre
from .outputs_planner import OutputPlan, plan_outputs
from .storyboard import Storyboard, build_storyboard_from_audio
from .transcription import TranscriptionUnavailable, transcribe_audio

JOBS_ROOT = "/tmp/music_story_video_ai_jobs"


@dataclass
class PipelineJob:
    id: str
    status: str = "queued"  # queued | analyzing | generating | assembling | done | error
    progress: str = ""
    error: Optional[str] = None
    provider: str = ""
    is_demo: bool = True
    storyboard: Optional[Storyboard] = None
    output_plan: Optional[OutputPlan] = None
    genre_detected: Optional[str] = None
    result_path: Optional[str] = None
    started_at: float = field(default_factory=time.time)


def run_pipeline(
    job: PipelineJob,
    generator: Generator,
    audio_path: str,
    director: DirectorSettings,
    lyrics_text: Optional[str] = None,
    character_photo_path: Optional[str] = None,
    genre_override: Optional[str] = None,
    transcribe: bool = True,
) -> None:
    job.provider = generator.name
    job.is_demo = not generator.is_real
    work_dir = f"{JOBS_ROOT}/{job.id}"
    Path(work_dir).mkdir(parents=True, exist_ok=True)

    try:
        job.status = "analyzing"

        job.progress = "Analyse audio : tempo, energie, structure du morceau..."
        audio_features = analyze_audio_file(audio_path)

        genre = genre_override
        if not genre:
            job.progress = "Classification automatique du genre musical..."
            try:
                prediction = classify_genre(audio_path)
                genre = prediction.app_genre
                job.genre_detected = f"{prediction.model_label} (confiance {prediction.confidence:.0%})"
            except GenreClassificationUnavailable as exc:
                genre = audio_features.suggested_genre_family()
                job.genre_detected = f"classification indisponible, suggestion approximative: {genre} ({exc})"

        transcription = None
        if transcribe and not lyrics_text:
            job.progress = "Transcription automatique des paroles (si presentes)..."
            try:
                transcription = transcribe_audio(audio_path)
            except TranscriptionUnavailable:
                transcription = None

        job.progress = "Construction du storyboard sur la duree reelle du morceau..."
        storyboard = build_storyboard_from_audio(
            audio_features, director, genre, lyrics_text=lyrics_text, transcription=transcription
        )
        job.storyboard = storyboard
        job.output_plan = plan_outputs(storyboard)

        job.status = "generating"
        character_reference_id = None
        if generator.is_real:
            job.progress = "Creation du personnage de reference (coherence entre les scenes)..."
            character_reference_id = ensure_character_reference(generator, director, character_photo_path)

        scene_clip_specs: list[tuple[str, float]] = []
        for i, scene in enumerate(storyboard.scenes):
            job.progress = f"Generation de la scene {i + 1}/{len(storyboard.scenes)} ({scene.section_label})..."
            image_asset = generator.generate_image(scene.image_prompt, character_reference_id=character_reference_id)
            video_asset = generator.generate_video_from_image(
                image_asset.url, scene.video_prompt, motion_hint=director.camera
            )
            local_path = video_assembler.download_asset(video_asset, work_dir, f"scene_{i:02d}")
            duration = max(0.5, (scene.end_seconds or 0.0) - (scene.start_seconds or 0.0))
            scene_clip_specs.append((local_path, duration))

        job.status = "assembling"
        job.progress = "Assemblage de la video finale avec la musique originale..."
        fitted_clips = [
            video_assembler.fit_clip_to_duration(path, duration, f"{work_dir}/fit_{i:02d}.mp4")
            for i, (path, duration) in enumerate(scene_clip_specs)
        ]
        concatenated = video_assembler.concat_clips(fitted_clips, f"{work_dir}/concatenated.mp4")
        final_path = video_assembler.mux_with_audio(concatenated, audio_path, f"{work_dir}/final.mp4")

        job.result_path = final_path
        job.status = "done"
        job.progress = "Clip termine."
    except GenerationError as exc:
        job.status = "error"
        job.error = str(exc)
    except video_assembler.AssemblyError as exc:
        job.status = "error"
        job.error = str(exc)
    except Exception as exc:  # pragma: no cover - safety net for unexpected pipeline failures
        job.status = "error"
        job.error = f"Erreur inattendue: {exc}"
