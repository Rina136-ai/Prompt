"""Builds a scene-by-scene storyboard from analyzed lyrics + director settings."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .audio_analysis import AudioFeatures
from .director import DirectorSettings
from .lyrics_analysis import LyricsSection, analyze_lyrics, overall_mood
from .prompt_builder import build_scene_prompt, build_video_motion_prompt

GENRE_STAGING: dict[str, str] = {
    "afrobeat": "un groupe de danseurs executant une chorégraphie afrobeat synchronisee",
    "amapiano": "des danseurs amapiano au groove bas, ambiance de block party",
    "makossa": "des danseurs makossa dans une fete de quartier",
    "bikutsi": "des danseurs bikutsi au rythme percussif rapide",
    "jazz": "une chanteuse de jazz sur scene, un saxophoniste et des musiciens dans un club enfume",
    "soul": "un ou deux personnages principaux dont les expressions suivent les paroles, mise en scene narrative",
    "gospel": "une chorale gospel et un soliste, lumiere chaude et emotive",
    "rnb": "un personnage principal filme en gros plans intimistes, eclairage tamise",
    "pop": "un artiste principal entoure de danseurs sur une scene de concert",
    "rock": "un groupe de rock sur scene avec guitares et batterie, foule en fond",
    "zouk": "un couple qui danse le zouk, mouvements lents et sensuels",
    "reggae": "un chanteur reggae en exterieur, ambiance detendue et ensoleillee",
    "salsa": "des couples de danseurs de salsa dans une salle animee",
}

_DEFAULT_STAGING = "des personnages dont les actions et emotions suivent le sens des paroles"


@dataclass
class Scene:
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


@dataclass
class Storyboard:
    genre: str
    overall_mood: str
    scenes: list[Scene] = field(default_factory=list)

    def highlight_scenes(self) -> list[Scene]:
        return [s for s in self.scenes if s.is_highlight]


_ENERGETIC_MOODS = {"joie", "colere", "celebration"}
_CALM_MOODS = {"tristesse", "nostalgie", "spiritualite"}


def _mood_based_energy(mood: str) -> str:
    if mood in _ENERGETIC_MOODS:
        return "energique"
    if mood in _CALM_MOODS:
        return "calme"
    return "modere"


def _energy_for_section(index: int, sections_count: int, mood: str, audio: Optional[AudioFeatures]) -> str:
    if audio and audio.segments:
        seg_index = min(int(index / max(sections_count, 1) * len(audio.segments)), len(audio.segments) - 1)
        return audio.segments[seg_index].energy
    return _mood_based_energy(mood)


def build_storyboard(
    lyrics: str,
    director: DirectorSettings,
    genre: str,
    audio: Optional[AudioFeatures] = None,
) -> Storyboard:
    sections: list[LyricsSection] = analyze_lyrics(lyrics)
    scenes: list[Scene] = []

    staging = GENRE_STAGING.get(genre.lower(), _DEFAULT_STAGING)
    genre_mood = overall_mood(sections)

    for section in sections:
        energy = _energy_for_section(section.index, len(sections), section.mood, audio)
        scene_description = f"{staging}, evoquant: \"{section.text.splitlines()[0][:80]}\""
        image_prompt = build_scene_prompt(
            scene_description=scene_description,
            mood=section.mood,
            genre=genre,
            director=director,
            energy=energy,
            is_chorus=section.is_chorus,
        )
        video_prompt = build_video_motion_prompt(image_prompt, director.camera)
        scenes.append(
            Scene(
                index=section.index,
                section_label=section.label,
                lyrics_excerpt=section.text,
                mood=section.mood,
                energy=energy,
                is_highlight=section.is_chorus,
                image_prompt=image_prompt,
                video_prompt=video_prompt,
            )
        )

    if audio and audio.duration and scenes:
        per_scene = audio.duration / len(scenes)
        for i, scene in enumerate(scenes):
            scene.start_seconds = round(i * per_scene, 2)
            scene.end_seconds = round((i + 1) * per_scene, 2)

    return Storyboard(genre=genre, overall_mood=genre_mood, scenes=scenes)
