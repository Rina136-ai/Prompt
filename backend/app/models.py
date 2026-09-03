from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class DirectorSettingsIn(BaseModel):
    characters: str = "diversite"
    characters_custom: Optional[str] = None
    style: str = "photorealiste"
    dance: str = "aucune"
    era: str = "contemporaine"
    decor: str = "studio"
    decor_custom: Optional[str] = None
    camera: str = "cinematographique"
    character_reference_media_id: Optional[str] = None
    extra_notes: str = ""


class StoryboardRequest(BaseModel):
    mode: str
    lyrics: str
    genre: str = "pop"
    director: DirectorSettingsIn
    audio_token: Optional[str] = None


class SceneOut(BaseModel):
    index: int
    section_label: str
    lyrics_excerpt: str
    mood: str
    energy: str
    is_highlight: bool
    image_prompt: str
    video_prompt: str
    start_seconds: Optional[float] = None
    end_seconds: Optional[float] = None


class ShortClipOut(BaseModel):
    title: str
    scene_indices: list[int]
    approx_seconds: float


class VariantOut(BaseModel):
    label: str
    style_override: str
    camera_override: str


class OutputPlanOut(BaseModel):
    main_clip_scene_indices: list[int]
    shorts: list[ShortClipOut]
    visualizer_mood: str
    lyric_video_scene_indices: list[int]
    image_scene_indices: list[int]
    variants: list[VariantOut]


class StoryboardResponse(BaseModel):
    genre: str
    overall_mood: str
    scenes: list[SceneOut]
    output_plan: OutputPlanOut
    audio_summary: Optional[dict] = None


class GenerateImageRequest(BaseModel):
    prompt: str
    character_reference_id: Optional[str] = None


class GenerateVideoFromImageRequest(BaseModel):
    image_url: str
    prompt: str
    motion_hint: Optional[str] = None


class GenerateAudioRequest(BaseModel):
    prompt: str
    duration_seconds: float = 30.0


class GeneratedAssetOut(BaseModel):
    kind: str
    url: str
    provider: str
    job_id: Optional[str] = None


class PipelineStartResponse(BaseModel):
    job_id: str


class PipelineStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: str
    error: Optional[str] = None
    provider: str
    is_demo: bool
    genre_detected: Optional[str] = None
    storyboard: Optional[StoryboardResponse] = None
    result_ready: bool = False
