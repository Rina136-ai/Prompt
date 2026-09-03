"""From one storyboard, plans the multi-output content set the concept describes:
one full clip, several short-form cuts, a visualizer, a lyric video, standalone
images, and alternate style variants -- all from a single song.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .storyboard import Scene, Storyboard

SHORT_MIN_SECONDS = 15
SHORT_MAX_SECONDS = 30
MAX_SHORTS = 3


@dataclass
class ShortClipPlan:
    title: str
    scene_indices: list[int]
    approx_seconds: float


@dataclass
class VariantPlan:
    label: str
    style_override: str
    camera_override: str


@dataclass
class OutputPlan:
    main_clip_scene_indices: list[int]
    shorts: list[ShortClipPlan]
    visualizer_mood: str
    lyric_video_scene_indices: list[int]
    image_scene_indices: list[int]
    variants: list[VariantPlan]


def _scene_duration(scene: Scene, fallback: float) -> float:
    if scene.start_seconds is not None and scene.end_seconds is not None:
        return scene.end_seconds - scene.start_seconds
    return fallback


def _plan_shorts(storyboard: Storyboard) -> list[ShortClipPlan]:
    highlights = storyboard.highlight_scenes() or storyboard.scenes[:1]
    fallback_duration = 6.0
    shorts: list[ShortClipPlan] = []
    for n, highlight in enumerate(highlights[:MAX_SHORTS], start=1):
        idx = highlight.index
        indices = [idx]
        total = _scene_duration(highlight, fallback_duration)

        neighbors = sorted(
            (s for s in storyboard.scenes if s.index != idx),
            key=lambda s: abs(s.index - idx),
        )
        for neighbor in neighbors:
            if total >= SHORT_MIN_SECONDS:
                break
            indices.append(neighbor.index)
            total += _scene_duration(neighbor, fallback_duration)

        indices.sort()
        total = min(total, SHORT_MAX_SECONDS)
        shorts.append(
            ShortClipPlan(
                title=f"Extrait {n} - {highlight.section_label}",
                scene_indices=indices,
                approx_seconds=round(total, 1),
            )
        )
    return shorts


def _plan_variants(storyboard: Storyboard) -> list[VariantPlan]:
    base_style = storyboard.scenes[0].mood if storyboard.scenes else "contemplation"
    alt_style = "vintage" if base_style != "vintage" else "cinema"
    return [
        VariantPlan(label="Version originale", style_override="", camera_override=""),
        VariantPlan(label="Version alternative (style)", style_override=alt_style, camera_override=""),
        VariantPlan(label="Version alternative (camera dynamique)", style_override="", camera_override="dynamique"),
    ]


def plan_outputs(storyboard: Storyboard) -> OutputPlan:
    scene_indices = [s.index for s in storyboard.scenes]
    return OutputPlan(
        main_clip_scene_indices=scene_indices,
        shorts=_plan_shorts(storyboard),
        visualizer_mood=storyboard.overall_mood,
        lyric_video_scene_indices=scene_indices,
        image_scene_indices=scene_indices,
        variants=_plan_variants(storyboard),
    )
