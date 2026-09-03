"""Builds a scene-by-scene storyboard, from lyrics and/or real audio structure."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .audio_analysis import AudioFeatures
from .director import DirectorSettings
from .lyrics_analysis import LyricsSection, analyze_lyrics, overall_mood, score_mood, split_into_blocks
from .prompt_builder import build_scene_prompt, build_video_motion_prompt
from .transcription import TranscriptionResult

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
    # Familles reconnues par le classificateur audio reel (genre_classifier.py) --
    # distinctes des genres regionaux ci-dessus, que le modele ne peut pas detecter.
    "blues": "un musicien de blues seul avec sa guitare dans un bar intimiste",
    "classique": "un orchestre ou un soliste dans une salle de concert, mise en scene elegante",
    "electro": "un DJ et une foule dans un club, jeux de lumiere synchronises",
    "rap": "un rappeur et son groupe dans une ambiance urbaine, decor de rue ou de studio",
}

_DEFAULT_STAGING = "des personnages dont les actions et emotions suivent le sens des paroles"
_DEFAULT_MOOD = "contemplation"


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

    def total_duration(self) -> float:
        if not self.scenes or self.scenes[-1].end_seconds is None:
            return 0.0
        return self.scenes[-1].end_seconds - (self.scenes[0].start_seconds or 0.0)


_ENERGETIC_MOODS = {"joie", "colere", "celebration"}
_CALM_MOODS = {"tristesse", "nostalgie", "spiritualite"}


def _mood_based_energy(mood: str) -> str:
    if mood in _ENERGETIC_MOODS:
        return "energique"
    if mood in _CALM_MOODS:
        return "calme"
    return "modere"


def _mood_from_energy(energy: str) -> str:
    if energy == "energique":
        return "celebration"
    if energy == "calme":
        return "contemplation"
    return "nostalgie"


def _energy_for_section(index: int, sections_count: int, mood: str, audio: Optional[AudioFeatures]) -> str:
    if audio and audio.sections:
        seg_index = min(int(index / max(sections_count, 1) * len(audio.sections)), len(audio.sections) - 1)
        return audio.sections[seg_index].energy
    return _mood_based_energy(mood)


def _dominant(values: list[str]) -> str:
    if not values:
        return _DEFAULT_MOOD
    counts: dict[str, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0]


def build_storyboard(
    lyrics: str,
    director: DirectorSettings,
    genre: str,
    audio: Optional[AudioFeatures] = None,
) -> Storyboard:
    """Lyrics-driven storyboard (modes: Paroles -> Images / Paroles + Musique -> Film).

    Requires non-empty lyrics. For audio-only input (no lyrics available),
    use build_storyboard_from_audio() instead -- that's the path for the
    "MP3 seul" priority flow.
    """
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


def build_storyboard_from_audio(
    audio: AudioFeatures,
    director: DirectorSettings,
    genre: str,
    lyrics_text: Optional[str] = None,
    transcription: Optional[TranscriptionResult] = None,
) -> Storyboard:
    """Audio-driven storyboard: works from real structural sections alone.

    This is the path for "MP3 seul" (no lyrics required at all). If
    `transcription` (timestamped) is available, its lines are matched to
    whichever detected section they fall in. Otherwise, if plain
    `lyrics_text` was typed by the user with no timing info, it is split
    into blocks and distributed evenly across the sections as a best-effort
    approximation (clearly weaker than real timestamps, but still gives the
    storyboard real words to work with instead of guessing).

    Every scene's start/end seconds come directly from the real detected
    song structure, so the storyboard always spans the song's actual
    duration -- never a fixed/assumed length.
    """
    staging = GENRE_STAGING.get(genre.lower(), _DEFAULT_STAGING)
    manual_blocks = split_into_blocks(lyrics_text) if lyrics_text and not transcription else []

    energy_rank = {"calme": 0, "modere": 1, "energique": 2}
    energetic_indices = {i for i, s in enumerate(audio.sections) if s.energy == "energique"}
    if not energetic_indices and audio.sections:
        energetic_indices = {max(range(len(audio.sections)), key=lambda i: energy_rank[audio.sections[i].energy])}

    scenes: list[Scene] = []
    for i, section in enumerate(audio.sections):
        excerpt = ""
        if transcription and transcription.lines:
            midpoints = [
                line.text for line in transcription.lines
                if section.start <= (line.start + line.end) / 2 < section.end
            ]
            excerpt = " ".join(midpoints).strip()
        elif manual_blocks:
            block_index = min(int(i / len(audio.sections) * len(manual_blocks)), len(manual_blocks) - 1)
            excerpt = manual_blocks[block_index]

        mood = score_mood(excerpt)[0] if excerpt else _mood_from_energy(section.energy)
        is_highlight = i in energetic_indices
        label = f"Section {i + 1}" + (" (moment fort)" if is_highlight else "")
        evocation = excerpt.splitlines()[0][:80] if excerpt else f"{section.energy}, ~{round(section.local_tempo_bpm)} BPM"
        scene_description = f"{staging}, evoquant: \"{evocation}\""

        image_prompt = build_scene_prompt(
            scene_description=scene_description,
            mood=mood,
            genre=genre,
            director=director,
            energy=section.energy,
            is_chorus=is_highlight,
        )
        video_prompt = build_video_motion_prompt(image_prompt, director.camera)

        scenes.append(
            Scene(
                index=i,
                section_label=label,
                lyrics_excerpt=excerpt,
                mood=mood,
                energy=section.energy,
                is_highlight=is_highlight,
                image_prompt=image_prompt,
                video_prompt=video_prompt,
                start_seconds=section.start,
                end_seconds=section.end,
            )
        )

    return Storyboard(genre=genre, overall_mood=_dominant([s.mood for s in scenes]), scenes=scenes)
