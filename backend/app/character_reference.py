"""Ensures the same character reappears across every generated scene.

Uses the provider's real character-consistency mechanism (Higgsfield's
"SoulId" / custom-references, see generators/higgsfield.py) when available:
either from a photo the user uploaded, or -- if none was given -- from one
auto-generated reference portrait, so a photorealistic-human clip doesn't
show a different person in every scene.
"""
from __future__ import annotations

import mimetypes
from typing import Optional

from .director import DirectorSettings, label
from .generators.base import GenerationError, Generator


def _reference_portrait_prompt(director: DirectorSettings) -> str:
    fragments = [
        "portrait photorealiste en gros plan d'un personnage principal",
        director.characters_phrase(),
        label(director.style),
        label(director.era),
        "visage net et detaille, eclairage cinematographique, arriere-plan neutre flou",
    ]
    return ", ".join(f for f in fragments if f)


def ensure_character_reference(
    generator: Generator,
    director: DirectorSettings,
    uploaded_photo_path: Optional[str] = None,
) -> Optional[str]:
    """Returns a character_reference_id to reuse across every scene's
    generate_image() call, or None if it couldn't be created (the pipeline
    then falls back to independent, non-consistent scene generation)."""
    try:
        if uploaded_photo_path:
            content_type = mimetypes.guess_type(uploaded_photo_path)[0] or "image/jpeg"
            source_url = generator.upload_file(uploaded_photo_path, content_type)
        else:
            portrait = generator.generate_image(_reference_portrait_prompt(director))
            source_url = portrait.url

        return generator.create_character_reference("Personnage principal", [source_url])
    except (GenerationError, NotImplementedError):
        return None
