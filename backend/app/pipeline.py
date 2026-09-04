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
from .character_reference import ensure_character_reference, ensure_provider_reference
from .director import DirectorSettings
from .generators.base import GenerationError, Generator
from .genre_classifier import GenreClassificationUnavailable, classify_genre
from .outputs_planner import OutputPlan, plan_outputs
from .project_dna import ProjectDNA, build_project_dna, persist_project_dna
from .storyboard import NarrativeStoryboard, Storyboard, build_storyboard_from_audio, build_storyboard_from_dna
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


# ---------------------------------------------------------------------------
# Two-phase flow (Project DNA / NarrativeStoryboard): Phase A is free (no
# generator call, ever); Phase B is the only phase that spends credits, and
# can be called on any subset of shots (preview) or all of them (full clip)
# against the SAME persisted RenderProject -- so the full clip never pays
# again for shots already rendered during the preview.
#
# PipelineJob / run_pipeline above are untouched and keep backing the
# existing /api/pipeline/run endpoint exactly as before.
# ---------------------------------------------------------------------------


@dataclass
class RenderProject:
    id: str
    status: str = "queued"  # queued | analyzing | ready | generating | assembling | error
    progress: str = ""
    error: Optional[str] = None
    audio_path: str = ""
    work_dir: str = ""
    genre_detected: Optional[str] = None
    dna: Optional[ProjectDNA] = None
    storyboard: Optional[NarrativeStoryboard] = None
    rendered_shots: dict[int, dict] = field(default_factory=dict)  # shot_index -> {"video_path": str}
    outputs: dict[str, str] = field(default_factory=dict)  # output_name -> final mp4 path
    created_at: float = field(default_factory=time.time)


def build_project(
    project: RenderProject,
    audio_path: str,
    director: DirectorSettings,
    lyrics_text: Optional[str] = None,
    character_photo_path: Optional[str] = None,
    genre_override: Optional[str] = None,
    transcribe: bool = True,
) -> None:
    """Phase A: analysis + Project DNA + full narrative storyboard. Never
    calls a Generator method, so it never spends a credit and can be re-run
    or inspected freely."""
    project.audio_path = audio_path
    project.work_dir = f"{JOBS_ROOT}/{project.id}"
    Path(project.work_dir).mkdir(parents=True, exist_ok=True)

    try:
        project.status = "analyzing"

        project.progress = "Analyse audio : tempo, energie, structure du morceau..."
        audio_features = analyze_audio_file(audio_path)

        genre = genre_override
        if not genre:
            project.progress = "Classification automatique du genre musical..."
            try:
                prediction = classify_genre(audio_path)
                genre = prediction.app_genre
                project.genre_detected = f"{prediction.model_label} (confiance {prediction.confidence:.0%})"
            except GenreClassificationUnavailable as exc:
                genre = audio_features.suggested_genre_family()
                project.genre_detected = f"classification indisponible, suggestion approximative: {genre} ({exc})"

        transcription = None
        if transcribe and not lyrics_text:
            project.progress = "Transcription automatique des paroles (si presentes)..."
            try:
                transcription = transcribe_audio(audio_path)
            except TranscriptionUnavailable:
                transcription = None

        project.progress = "Construction du Project DNA (comprehension globale, casting, style)..."
        dna = build_project_dna(
            audio_features,
            genre,
            director,
            lyrics_text=lyrics_text,
            transcription=transcription,
            character_photo_path=character_photo_path,
            project_id=project.id,
        )
        project.dna = dna

        project.progress = "Construction du storyboard narratif (scenes -> plans)..."
        project.storyboard = build_storyboard_from_dna(
            dna, audio_features.sections, lyrics_text=lyrics_text, transcription=transcription
        )

        persist_project_dna(dna, f"{project.work_dir}/dna.json")

        project.status = "ready"
        project.progress = "Analyse terminee. Pret pour l'apercu ou le clip complet."
    except Exception as exc:  # pragma: no cover - safety net
        project.status = "error"
        project.error = f"Erreur lors de l'analyse: {exc}"


def render_shots(
    project: RenderProject,
    generator: Generator,
    shot_indices: list[int],
    output_name: str,
    shot_duration_overrides: Optional[dict[int, float]] = None,
) -> Optional[str]:
    """Phase B: generates (or reuses already-rendered) shots for the given
    subset, assembles them, and muxes with the matching slice of the
    original audio. Called with the preview's shot indices for the preview,
    and with every shot index for the full clip -- shots already rendered
    (tracked in `project.rendered_shots`) are never regenerated or re-billed.

    `shot_duration_overrides` (shot.index -> shorter duration) lets a caller
    (see outputs_planner.plan_preview's precise end-trim) render a shot for
    less than its full storyboard span, so a preview window can be capped at
    an exact maximum duration without dropping a whole shot.
    """
    shot_duration_overrides = shot_duration_overrides or {}
    if project.dna is None or project.storyboard is None:
        project.status = "error"
        project.error = "Le projet n'a pas encore ete analyse (build_project doit etre appele avant render_shots)."
        return None

    try:
        dna = project.dna
        shots_by_index = {shot.index: shot for shot in project.storyboard.all_shots()}
        requested_shots = [shots_by_index[i] for i in shot_indices if i in shots_by_index]
        if not requested_shots:
            raise GenerationError("Aucun plan valide a generer pour ce sous-ensemble.")

        project.status = "generating"
        style_hint = ", ".join(f for f in [dna.style.visual_style, dna.style.era, dna.style.decor_family] if f)

        if generator.is_real:
            for character in dna.characters:
                project.progress = f"Resolution du personnage de reference: {character.role}..."
                ensure_provider_reference(generator, character, style_hint=style_hint)

        fitted_clips: list[str] = []
        for n, shot in enumerate(requested_shots):
            if shot.index in project.rendered_shots:
                local_video_path = project.rendered_shots[shot.index]["video_path"]
            else:
                project.progress = f"Generation du plan {n + 1}/{len(requested_shots)} (plan #{shot.index})..."
                lead_character = dna.character_by_id(shot.character_ids[0]) if shot.character_ids else None
                reference_id = lead_character.provider_refs.get(generator.name) if lead_character else None

                image_asset = generator.generate_image(shot.image_prompt, character_reference_id=reference_id)
                video_asset = generator.generate_video_from_image(image_asset.url, shot.video_prompt)
                local_video_path = video_assembler.download_asset(video_asset, project.work_dir, f"shot_{shot.index:03d}")
                project.rendered_shots[shot.index] = {"video_path": local_video_path}

            natural_duration = shot.end_seconds - shot.start_seconds
            duration = max(0.5, shot_duration_overrides.get(shot.index, natural_duration))
            fitted_path = f"{project.work_dir}/fit_{shot.index:03d}_{output_name}.mp4"
            video_assembler.fit_clip_to_duration(local_video_path, duration, fitted_path)
            fitted_clips.append(fitted_path)

        project.status = "assembling"
        project.progress = f"Assemblage de '{output_name}'..."
        concatenated = f"{project.work_dir}/concatenated_{output_name}.mp4"
        video_assembler.concat_clips(fitted_clips, concatenated)

        last_shot = requested_shots[-1]
        last_shot_duration = shot_duration_overrides.get(last_shot.index, last_shot.end_seconds - last_shot.start_seconds)
        start = requested_shots[0].start_seconds
        end = last_shot.start_seconds + last_shot_duration
        covers_full_song = start <= 0.01 and end >= dna.duration_seconds - 0.5
        if covers_full_song:
            audio_path_for_mux = project.audio_path
        else:
            audio_path_for_mux = f"{project.work_dir}/audio_{output_name}.wav"
            video_assembler.extract_audio_segment(project.audio_path, start, end, audio_path_for_mux)

        final_path = f"{project.work_dir}/final_{output_name}.mp4"
        video_assembler.mux_with_audio(concatenated, audio_path_for_mux, final_path)

        project.outputs[output_name] = final_path
        project.status = "ready"
        project.progress = f"'{output_name}' termine."
        return final_path
    except GenerationError as exc:
        project.status = "error"
        project.error = str(exc)
        return None
    except video_assembler.AssemblyError as exc:
        project.status = "error"
        project.error = str(exc)
        return None
    except Exception as exc:  # pragma: no cover - safety net
        project.status = "error"
        project.error = f"Erreur inattendue: {exc}"
        return None
