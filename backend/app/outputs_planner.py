"""From one storyboard, plans the multi-output content set the concept describes:
one full clip, several short-form cuts, a visualizer, a lyric video, standalone
images, and alternate style variants -- all from a single song.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .storyboard import NarrativeStoryboard, Scene, Storyboard

SHORT_MIN_SECONDS = 15
SHORT_MAX_SECONDS = 30
MAX_SHORTS = 3

PREVIEW_MIN_SECONDS = 20.0
PREVIEW_MAX_SECONDS = 30.0
PREVIEW_TARGET_SECONDS = 25.0


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


# ---------------------------------------------------------------------------
# Preview selection (Project DNA / NarrativeStoryboard flow).
#
# Correction: the representative excerpt is NOT just the highest-energy
# passage. Each NarrativeScene already carries a `combined_score` (energy +
# emotion + narrative importance + chorus bonus, see storyboard.py) and this
# picks the contiguous window of scenes whose combined score is highest
# while fitting the target duration -- a proper windowed search, not a
# "expand from the single energy peak" heuristic.
# ---------------------------------------------------------------------------


@dataclass
class PreviewPlan:
    shot_indices: list[int]
    scene_indices: list[int]
    start_seconds: float
    end_seconds: float
    approx_seconds: float


def plan_preview(
    storyboard: NarrativeStoryboard,
    target_seconds: float = PREVIEW_TARGET_SECONDS,
    min_seconds: float = PREVIEW_MIN_SECONDS,
    max_seconds: float = PREVIEW_MAX_SECONDS,
) -> PreviewPlan:
    scenes = storyboard.scenes
    if not scenes:
        return PreviewPlan(shot_indices=[], scene_indices=[], start_seconds=0.0, end_seconds=0.0, approx_seconds=0.0)

    n = len(scenes)
    # (in_range, score, distance_to_target, i, j, duration) for every contiguous window
    candidates: list[tuple[bool, float, float, int, int, float]] = []
    for i in range(n):
        duration = 0.0
        score = 0.0
        for j in range(i, n):
            duration += scenes[j].duration
            score += scenes[j].combined_score
            if duration > max_seconds * 2:
                break
            in_range = min_seconds <= duration <= max_seconds
            candidates.append((in_range, score, abs(duration - target_seconds), i, j, duration))

    in_range = [c for c in candidates if c[0]]
    if in_range:
        # Highest combined score wins; ties broken by closeness to the target duration.
        best = max(in_range, key=lambda c: (c[1], -c[2]))
    elif candidates:
        # No window fits [min,max] (e.g. a very short song) -- take the
        # closest-to-target duration available rather than failing.
        best = min(candidates, key=lambda c: c[2])
    else:
        best = (False, 0.0, 0.0, 0, n - 1, sum(s.duration for s in scenes))

    _, _, _, i, j, duration = best
    window = scenes[i : j + 1]
    shot_indices = [shot.index for scene in window for shot in scene.shots]

    return PreviewPlan(
        shot_indices=shot_indices,
        scene_indices=[s.index for s in window],
        start_seconds=window[0].start_seconds,
        end_seconds=window[-1].end_seconds,
        approx_seconds=round(duration, 1),
    )
