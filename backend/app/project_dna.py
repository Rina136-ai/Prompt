"""Project DNA: one provider-agnostic understanding of the whole song, built
once (free, no generation call) from audio + lyrics analysis, then reused
identically for both the preview and the full clip.

Casting comes from the story (lyrics/transcription), never from the genre.
Genre only ever feeds the StyleBible (atmosphere/decor/wardrobe), through
storyboard.GENRE_STAGING -- it is never read as a signal for who appears.
Promotion of a detected figure (see lyrics_analysis.detect_figures) into an
actual visible CharacterProfile is deliberately conservative: solo mentions
never count (the narrator already exists), abstract/spiritual referents are
excluded, and a figure needs to recur across at least
MIN_FIGURE_OCCURRENCES_FOR_CAST segments before it earns a face.
"""
from __future__ import annotations

import dataclasses
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from .audio_analysis import AudioFeatures
from .director import DirectorSettings, label
from .lyrics_analysis import detect_figures, score_mood, split_into_blocks
from .storyboard import GENRE_STAGING
from .transcription import TranscriptionResult

MIN_FIGURE_OCCURRENCES_FOR_CAST = 2


@dataclass
class CharacterProfile:
    id: str
    role: str
    description: str
    source_image_path: Optional[str] = None
    provider_refs: dict[str, str] = field(default_factory=dict)


@dataclass
class ReferencedPresence:
    """Something the lyrics address/evoke without becoming a visible, cast character."""

    pronoun_type: str
    reason: str


@dataclass
class StyleBible:
    visual_style: str
    era: str
    decor_family: str
    camera_language: str
    genre_staging_base: str  # atmosphere only -- never a casting signal


@dataclass
class NarrativeArc:
    synopsis: str
    mood_progression: list[str] = field(default_factory=list)
    thematic_keywords: list[str] = field(default_factory=list)


@dataclass
class ProjectDNA:
    id: str
    genre: str
    duration_seconds: float
    tempo_bpm: float
    style: StyleBible
    narrative: NarrativeArc
    characters: list[CharacterProfile]
    referenced_presences: list[ReferencedPresence] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def character_by_id(self, character_id: str) -> Optional[CharacterProfile]:
        return next((c for c in self.characters if c.id == character_id), None)


def _text_segments(lyrics_text: Optional[str], transcription: Optional[TranscriptionResult]) -> list[str]:
    if transcription and transcription.lines:
        return [line.text for line in transcription.lines if line.text.strip()]
    if lyrics_text and lyrics_text.strip():
        return split_into_blocks(lyrics_text)
    return []


def _build_style_bible(genre: str, director: DirectorSettings) -> StyleBible:
    return StyleBible(
        visual_style=label(director.style),
        era=label(director.era),
        decor_family=director.decor_phrase(),
        camera_language=label(director.camera),
        genre_staging_base=GENRE_STAGING.get(genre.lower(), ""),
    )


def _build_narrative_arc(text_segments: list[str]) -> NarrativeArc:
    if not text_segments:
        return NarrativeArc(
            synopsis="Morceau instrumental ou paroles indisponibles : pas de synopsis textuel, la mise en scene suit uniquement l'energie et la structure musicale.",
        )
    moods: list[str] = []
    keywords: set[str] = set()
    for segment in text_segments:
        mood, hits = score_mood(segment)
        moods.append(mood)
        keywords.update(hits)
    dominant = max(set(moods), key=moods.count)
    synopsis = (
        f"Une chanson dont l'humeur dominante est '{dominant}', "
        f"traversant {len(moods)} moments distincts."
    )
    return NarrativeArc(synopsis=synopsis, mood_progression=moods, thematic_keywords=sorted(keywords))


def _build_cast(
    text_segments: list[str],
    director: DirectorSettings,
    character_photo_path: Optional[str],
) -> tuple[list[CharacterProfile], list[ReferencedPresence]]:
    principal = CharacterProfile(
        id="figure_principale",
        role="narrateur_principal",
        description=f"personnage principal, {director.characters_phrase()}",
        source_image_path=character_photo_path,
    )
    characters = [principal]
    referenced: list[ReferencedPresence] = []

    if not text_segments:
        return characters, referenced

    for hint in detect_figures(text_segments):
        if hint.pronoun_type == "solo":
            continue  # the narrator is already the principal character

        if hint.likely_abstract:
            referenced.append(
                ReferencedPresence(
                    pronoun_type=hint.pronoun_type,
                    reason="reference probablement abstraite/spirituelle (dieu, ciel, destin...), non incarnee",
                )
            )
            continue

        if hint.occurrences < MIN_FIGURE_OCCURRENCES_FOR_CAST:
            referenced.append(
                ReferencedPresence(
                    pronoun_type=hint.pronoun_type,
                    reason=f"mention trop isolee ({hint.occurrences} occurrence(s)) pour justifier un personnage",
                )
            )
            continue

        if hint.pronoun_type == "duo":
            characters.append(
                CharacterProfile(
                    id="figure_secondaire",
                    role="figure_secondaire",
                    description="second personnage evoque de maniere recurrente dans les paroles",
                )
            )
        elif hint.pronoun_type == "collectif":
            characters.append(
                CharacterProfile(
                    id="groupe",
                    role="groupe",
                    description="groupe/foule evoque de maniere recurrente dans les paroles",
                )
            )

    return characters, referenced


def build_project_dna(
    audio_features: AudioFeatures,
    genre: str,
    director: DirectorSettings,
    lyrics_text: Optional[str] = None,
    transcription: Optional[TranscriptionResult] = None,
    character_photo_path: Optional[str] = None,
    project_id: Optional[str] = None,
) -> ProjectDNA:
    text_segments = _text_segments(lyrics_text, transcription)
    style = _build_style_bible(genre, director)
    narrative = _build_narrative_arc(text_segments)
    characters, referenced = _build_cast(text_segments, director, character_photo_path)

    return ProjectDNA(
        id=project_id or uuid.uuid4().hex,
        genre=genre,
        duration_seconds=audio_features.duration,
        tempo_bpm=audio_features.tempo_bpm,
        style=style,
        narrative=narrative,
        characters=characters,
        referenced_presences=referenced,
    )


def persist_project_dna(dna: ProjectDNA, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dataclasses.asdict(dna), f, ensure_ascii=False, indent=2)


def load_project_dna(path: str) -> ProjectDNA:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data["style"] = StyleBible(**data["style"])
    data["narrative"] = NarrativeArc(**data["narrative"])
    data["characters"] = [CharacterProfile(**c) for c in data["characters"]]
    data["referenced_presences"] = [ReferencedPresence(**r) for r in data.get("referenced_presences", [])]
    return ProjectDNA(**data)
