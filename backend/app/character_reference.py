"""Ensures the same character reappears across every generated scene.

Uses the provider's real character-consistency mechanism (Higgsfield's
"SoulId" / custom-references, see generators/higgsfield.py) when available:
either from a photo the user uploaded, or -- if none was given -- from one
auto-generated reference portrait, so a photorealistic-human clip doesn't
show a different person in every scene.
"""
from __future__ import annotations

import mimetypes
from typing import TYPE_CHECKING, Optional

from .director import DirectorSettings, label
from .generators.base import GenerationError, Generator

if TYPE_CHECKING:
    from .project_dna import CharacterProfile


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


# ---------------------------------------------------------------------------
# Project DNA flow: several persistent characters, resolved one at a time.
# `ensure_character_reference` above is untouched and keeps serving the
# single-character legacy pipeline (run_pipeline / /api/pipeline/run).
# ---------------------------------------------------------------------------


def _character_portrait_prompt(character: "CharacterProfile", style_hint: str = "") -> str:
    fragments = [
        "portrait photorealiste en gros plan",
        character.description,
        style_hint,
        "visage net et detaille, eclairage cinematographique, arriere-plan neutre flou",
    ]
    return ", ".join(f for f in fragments if f)


def ensure_provider_reference(
    generator: Generator,
    character: "CharacterProfile",
    style_hint: str = "",
) -> Optional[str]:
    """Per-character equivalent of ensure_character_reference(): resolves a
    provider-specific reference id for ONE CharacterProfile from the Project
    DNA, supporting several persistent characters with distinct roles by
    being called once per character rather than once globally.

    The result is cached on `character.provider_refs[generator.name]` -- a
    character already resolved (e.g. during a preview) is never re-resolved
    (and never re-charged) when rendering the full clip afterwards.
    """
    cached = character.provider_refs.get(generator.name)
    if cached:
        return cached

    try:
        if character.source_image_path:
            content_type = mimetypes.guess_type(character.source_image_path)[0] or "image/jpeg"
            source_url = generator.upload_file(character.source_image_path, content_type)
        else:
            portrait = generator.generate_image(_character_portrait_prompt(character, style_hint))
            source_url = portrait.url

        reference_id = generator.create_character_reference(character.id, [source_url])
    except (GenerationError, NotImplementedError):
        return None

    character.provider_refs[generator.name] = reference_id
    return reference_id
