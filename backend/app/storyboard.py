"""Builds a scene-by-scene storyboard, from lyrics and/or real audio structure."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Optional

from .audio_analysis import AudioFeatures, AudioSection
from .director import DirectorSettings
from .lyrics_analysis import LyricsSection, analyze_lyrics, detect_figures, overall_mood, score_mood, split_into_blocks
from .prompt_builder import build_scene_prompt, build_video_motion_prompt
from .transcription import TranscriptionResult

if TYPE_CHECKING:
    from .project_dna import ProjectDNA

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


# ---------------------------------------------------------------------------
# Narrative layer (Project DNA-driven): section musicale -> scene narrative -> plans.
#
# Everything above this line (Scene, Storyboard, build_storyboard,
# build_storyboard_from_audio) is untouched and keeps powering the existing
# lyrics-required advanced mode. This section is purely additive and backs
# the new Project DNA flow: a NarrativeScene groups 1..N real audio sections
# by narrative coherence (not a fixed 1-to-1 mapping), and a NarrativeScene
# decomposes into 1..N Shot -- the actual generation unit -- whose count and
# duration are decided by editing rhythm (energy + narrative role + scene
# duration), never by how many audio sections happen to underlie it. Audio
# section boundaries are only used as an optional hint for where to place a
# cut when one falls close to an already-planned cut point.
# ---------------------------------------------------------------------------

_TARGET_SHOT_SECONDS = {"energique": 3.5, "modere": 6.0, "calme": 9.0}
_ROLE_SHOT_BIAS = {
    "refrain": 0.7,
    "montee": 0.85,
    "introduction": 1.1,
    "conclusion": 1.1,
    "pont": 1.2,
    "couplet": 1.0,
}
MIN_SHOT_SECONDS = 2.5
MAX_SHOT_SECONDS = 12.0
MAX_NARRATIVE_SCENE_SECONDS = 28.0

NARRATIVE_IMPORTANCE = {
    "refrain": 1.0,
    "montee": 0.7,
    "pont": 0.6,
    "couplet": 0.5,
    "introduction": 0.3,
    "conclusion": 0.3,
}

_DNA_ENERGY_ACTION = {
    "energique": "mouvement vif, energie haute, coupes rapides",
    "modere": "mouvement fluide, energie moderee",
    "calme": "mouvement lent, ambiance intimiste",
}

_ENERGY_RANK = {"calme": 0, "modere": 1, "energique": 2}


@dataclass
class Shot:
    """The actual generation unit: one Shot = one image generation + one
    image-to-video generation. Several Shot make up one NarrativeScene."""

    index: int
    start_seconds: float
    end_seconds: float
    character_ids: list[str]
    image_prompt: str
    video_prompt: str

    @property
    def duration(self) -> float:
        return self.end_seconds - self.start_seconds


@dataclass
class NarrativeScene:
    """A unit of story, not of raw audio: may span several real audio sections."""

    index: int
    role: str  # introduction | couplet | montee | refrain | pont | conclusion
    start_seconds: float
    end_seconds: float
    energy: str
    mood: str
    is_chorus_scene: bool
    narrative_importance_score: float
    emotion_score: float
    character_ids: list[str]
    shots: list[Shot] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end_seconds - self.start_seconds

    @property
    def combined_score(self) -> float:
        """Used by outputs_planner.plan_preview() -- energy + emotion + narrative
        importance + chorus bonus, never energy alone."""
        energy_score = {"calme": 0.3, "modere": 0.6, "energique": 1.0}.get(self.energy, 0.5)
        chorus_bonus = 1.0 if self.is_chorus_scene else 0.0
        return (
            0.3 * energy_score
            + 0.25 * self.emotion_score
            + 0.25 * self.narrative_importance_score
            + 0.2 * chorus_bonus
        )


@dataclass
class NarrativeStoryboard:
    dna_id: str
    genre: str
    scenes: list[NarrativeScene] = field(default_factory=list)

    def all_shots(self) -> list[Shot]:
        return sorted((shot for scene in self.scenes for shot in scene.shots), key=lambda s: s.index)

    def total_duration(self) -> float:
        shots = self.all_shots()
        if not shots:
            return 0.0
        return shots[-1].end_seconds - shots[0].start_seconds


def _text_similarity(a: str, b: str) -> float:
    normalize = lambda t: re.sub(r"[^a-z0-9 ]", "", t.lower()).strip()  # noqa: E731
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def _detect_repeated_excerpts(excerpts: list[str], threshold: float = 0.72) -> list[bool]:
    repeated = [False] * len(excerpts)
    for i, a in enumerate(excerpts):
        if not a.strip():
            continue
        for j, b in enumerate(excerpts):
            if i != j and b.strip() and _text_similarity(a, b) >= threshold:
                repeated[i] = True
                break
    return repeated


def _excerpt_for_dna_section(
    section: AudioSection,
    transcription: Optional[TranscriptionResult],
    manual_blocks: list[str],
    index: int,
    total: int,
) -> str:
    if transcription and transcription.lines:
        lines = [
            line.text for line in transcription.lines
            if section.start <= (line.start + line.end) / 2 < section.end
        ]
        return " ".join(lines).strip()
    if manual_blocks:
        block_index = min(int(index / total * len(manual_blocks)), len(manual_blocks) - 1)
        return manual_blocks[block_index]
    return ""


def _aggregate_energy(audio_sections: list[AudioSection], indices: list[int]) -> str:
    energies = [audio_sections[i].energy for i in indices]
    return max(set(energies), key=energies.count)


def _assign_role(group_index: int, total_groups: int, is_chorus_scene: bool, energy_now: str, energy_prev: Optional[str]) -> str:
    if group_index == 0:
        return "introduction"
    if group_index == total_groups - 1:
        return "conclusion"
    if is_chorus_scene:
        return "refrain"
    if energy_prev is not None and _ENERGY_RANK.get(energy_now, 1) > _ENERGY_RANK.get(energy_prev, 1):
        return "montee"
    return "couplet"


def _emotion_score(mood: str, excerpt: str) -> float:
    if excerpt:
        _, hits = score_mood(excerpt)
        return min(1.0, len(hits) / 3.0) if hits else 0.15
    # No text available: a calm audio-only scene can still carry real emotion,
    # so this is not simply "high energy = high emotion".
    return 0.4 if mood != _DEFAULT_MOOD else 0.2


def _group_sections_for_dna(
    audio_sections: list[AudioSection],
    moods: list[str],
    is_repeated: list[bool],
) -> list[list[int]]:
    """Groups adjacent audio sections into narrative scenes.

    Two adjacent sections merge into the same scene only if they share a
    mood AND agree on being (or not being) a repeated/chorus-like block, and
    the merged scene doesn't exceed MAX_NARRATIVE_SCENE_SECONDS. This is the
    mechanism that lets a NarrativeScene span several sections instead of a
    fixed 1-to-1 mapping.
    """
    groups: list[list[int]] = [[0]]
    for i in range(1, len(audio_sections)):
        prev_idx = groups[-1][-1]
        same_mood = moods[i] == moods[prev_idx]
        same_repetition_state = is_repeated[i] == is_repeated[prev_idx]
        candidate_duration = audio_sections[i].end - audio_sections[groups[-1][0]].start
        if same_mood and same_repetition_state and candidate_duration <= MAX_NARRATIVE_SCENE_SECONDS:
            groups[-1].append(i)
        else:
            groups.append([i])
    return groups


def plan_shots_for_scene(
    start_seconds: float,
    end_seconds: float,
    energy: str,
    role: str,
    boundary_hints: Optional[list[float]] = None,
) -> list[tuple[float, float]]:
    """Decides how many shots a narrative scene gets and how long each is.

    Driven by scene duration, energy, and narrative role -- NEVER by how many
    audio sections underlie the scene. `boundary_hints` (real audio section
    boundaries within the scene) are used only to nudge a cut to a nearby
    real musical change point when one exists close enough; they never
    change how many shots are planned.
    """
    duration = end_seconds - start_seconds
    if duration <= 0:
        return [(start_seconds, end_seconds)]

    target = _TARGET_SHOT_SECONDS.get(energy, 6.0) * _ROLE_SHOT_BIAS.get(role, 1.0)
    target = max(MIN_SHOT_SECONDS, min(MAX_SHOT_SECONDS, target))
    n_shots = max(1, round(duration / target))

    cuts = [start_seconds + duration * i / n_shots for i in range(n_shots + 1)]

    if boundary_hints and n_shots > 1:
        tolerance = min(3.0, duration / (2 * n_shots))
        snapped = [cuts[0]]
        for cut in cuts[1:-1]:
            nearest = min(boundary_hints, key=lambda b: abs(b - cut))
            snapped.append(nearest if abs(nearest - cut) <= tolerance else cut)
        snapped.append(cuts[-1])
        cuts = sorted(set(round(c, 2) for c in snapped))

    if len(cuts) < 2:
        cuts = [start_seconds, end_seconds]

    shots = list(zip(cuts, cuts[1:]))

    merged: list[tuple[float, float]] = []
    for s, e in shots:
        if merged and (e - merged[-1][0]) < MIN_SHOT_SECONDS:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    return merged


def _character_fragment(dna: "ProjectDNA", character_ids: list[str]) -> str:
    descriptions = [c.description for cid in character_ids if (c := dna.character_by_id(cid))]
    return ", ".join(descriptions)


_ROLE_TO_PRONOUN_TYPE = {"figure_secondaire": "duo", "groupe": "collectif"}


def _select_scene_characters(dna: "ProjectDNA", scene_excerpt: str) -> list[str]:
    """Conservative, story-driven casting for ONE narrative scene.

    The Project DNA's character list is the film's global cast, not a
    per-scene guarantee: a secondary/group character only appears in a
    scene when THIS scene's own text gives local evidence for it (the same
    conservative detect_figures() signal used to build the DNA in the first
    place, re-applied to just this scene's window). The principal character
    is always the safe default -- when a scene has no text at all (audio
    only, or nothing matched this window), or the evidence is ambiguous, we
    fall back to the principal alone rather than adding anyone.
    """
    principal = next((c for c in dna.characters if c.role == "narrateur_principal"), None)
    selected: list[str] = [principal.id] if principal else []

    if not scene_excerpt:
        return selected

    local_hints = {hint.pronoun_type: hint for hint in detect_figures([scene_excerpt])}

    for character in dna.characters:
        pronoun_type = _ROLE_TO_PRONOUN_TYPE.get(character.role)
        if pronoun_type is None:
            continue  # not a duo/groupe-style character (e.g. the principal, already included)
        hint = local_hints.get(pronoun_type)
        if hint and not hint.likely_abstract:
            selected.append(character.id)

    return selected


def build_storyboard_from_dna(
    dna: "ProjectDNA",
    audio_sections: list[AudioSection],
    lyrics_text: Optional[str] = None,
    transcription: Optional[TranscriptionResult] = None,
) -> NarrativeStoryboard:
    """The new chain: real audio sections -> narrative scenes (Project DNA
    style/cast) -> shots (editing-rhythm driven). Requires a ProjectDNA
    already built by project_dna.build_project_dna() so casting/style are
    decided once, globally, before any scene is planned.
    """
    if not audio_sections:
        return NarrativeStoryboard(dna_id=dna.id, genre=dna.genre, scenes=[])

    manual_blocks = split_into_blocks(lyrics_text) if lyrics_text and not transcription else []

    excerpts = [
        _excerpt_for_dna_section(section, transcription, manual_blocks, i, len(audio_sections))
        for i, section in enumerate(audio_sections)
    ]
    moods = [
        score_mood(excerpt)[0] if excerpt else _mood_from_energy(audio_sections[i].energy)
        for i, excerpt in enumerate(excerpts)
    ]
    is_repeated = _detect_repeated_excerpts(excerpts)

    groups = _group_sections_for_dna(audio_sections, moods, is_repeated)

    scenes: list[NarrativeScene] = []
    prev_energy: Optional[str] = None
    shot_counter = 0

    for g_index, indices in enumerate(groups):
        start = audio_sections[indices[0]].start
        end = audio_sections[indices[-1]].end
        energy = _aggregate_energy(audio_sections, indices)
        is_chorus_scene = any(is_repeated[i] for i in indices)
        role = _assign_role(g_index, len(groups), is_chorus_scene, energy, prev_energy)
        prev_energy = energy

        group_moods = [moods[i] for i in indices]
        scene_mood = max(set(group_moods), key=group_moods.count)
        combined_excerpt = " ".join(excerpts[i] for i in indices if excerpts[i]).strip()
        emotion_score = _emotion_score(scene_mood, combined_excerpt)
        narrative_importance = NARRATIVE_IMPORTANCE.get(role, 0.5)

        # Story-driven, conservative per-scene casting: the DNA's full cast is
        # the film's global cast, not a guarantee that everyone appears in
        # every scene (see _select_scene_characters).
        character_ids = _select_scene_characters(dna, combined_excerpt)

        boundary_hints = [audio_sections[i].start for i in indices] + [audio_sections[i].end for i in indices]
        shot_ranges = plan_shots_for_scene(start, end, energy, role, boundary_hints=boundary_hints)

        shots: list[Shot] = []
        staging = dna.style.genre_staging_base or _DEFAULT_STAGING
        for shot_start, shot_end in shot_ranges:
            evocation = combined_excerpt.splitlines()[0][:80] if combined_excerpt else f"{energy}, role {role}"
            scene_description = f"{staging}, evoquant: \"{evocation}\""
            image_prompt = ", ".join(
                part for part in [
                    scene_description,
                    f"genre musical: {dna.genre}",
                    f"ambiance: {scene_mood}",
                    dna.style.visual_style,
                    dna.style.era,
                    dna.style.decor_family,
                    dna.style.camera_language,
                    _character_fragment(dna, character_ids),
                    _DNA_ENERGY_ACTION.get(energy, ""),
                    "moment fort du refrain, mise en scene la plus spectaculaire" if is_chorus_scene else "",
                ]
                if part
            )
            video_prompt = (
                f"{image_prompt}, camera: {dna.style.camera_language}, "
                "video courte avec mouvement naturel et cadrage stable"
            )
            shots.append(
                Shot(
                    index=shot_counter,
                    start_seconds=round(shot_start, 2),
                    end_seconds=round(shot_end, 2),
                    character_ids=character_ids,
                    image_prompt=image_prompt,
                    video_prompt=video_prompt,
                )
            )
            shot_counter += 1

        scenes.append(
            NarrativeScene(
                index=g_index,
                role=role,
                start_seconds=round(start, 2),
                end_seconds=round(end, 2),
                energy=energy,
                mood=scene_mood,
                is_chorus_scene=is_chorus_scene,
                narrative_importance_score=narrative_importance,
                emotion_score=emotion_score,
                character_ids=character_ids,
                shots=shots,
            )
        )

    return NarrativeStoryboard(dna_id=dna.id, genre=dna.genre, scenes=scenes)
