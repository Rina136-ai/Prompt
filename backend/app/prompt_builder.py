"""Builds the text prompt sent to the image/video generator for one scene."""
from __future__ import annotations

from .director import DirectorSettings, label

_ENERGY_ACTION = {
    "energique": "mouvement vif, energie haute, coupes rapides",
    "modere": "mouvement fluide, energie moderee",
    "calme": "mouvement lent, ambiance intimiste",
}


def build_scene_prompt(
    *,
    scene_description: str,
    mood: str,
    genre: str,
    director: DirectorSettings,
    energy: str = "modere",
    is_chorus: bool = False,
) -> str:
    """Compose a single natural-language prompt describing the scene to generate."""
    parts = [scene_description]
    parts.append(f"genre musical: {genre}")
    parts.append(f"ambiance: {mood}")
    parts.extend(director.as_prompt_fragments())
    parts.append(_ENERGY_ACTION.get(energy, _ENERGY_ACTION["modere"]))
    if is_chorus:
        parts.append("moment fort du refrain, mise en scene la plus spectaculaire")
    return ", ".join(p for p in parts if p)


def build_video_motion_prompt(scene_prompt: str, camera: str) -> str:
    return f"{scene_prompt}, camera: {label(camera)}, video court avec mouvement naturel et cadrage stable"
