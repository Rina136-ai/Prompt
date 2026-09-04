"""Regression: genre may color aesthetics (editing rhythm, camera movement,
texture, light, movement quality) but must NEVER inject a place, an
instrument, a profession/role, a character, or a narrative action. Same
audio + same lyrics + same Project DNA narrative content, with two
different genre classifications, must change the look, never the story."""
import re

from app.audio_analysis import AudioFeatures, AudioSection
from app.director import DirectorSettings
from app.project_dna import build_project_dna
from app.storyboard import GENRE_STAGING, build_storyboard_from_dna

# Concrete instances of what the ban covers: lieu, instrument, metier/role,
# personnage, action narrative. Checked against EVERY genre's aesthetic
# text, not just the one that revealed the problem (Blues).
FORBIDDEN_NARRATIVE_NOUNS = [
    # lieu
    "bar", "club", "rue", "studio", "scene de concert", "salle", "quartier", "exterieur",
    # instrument
    "guitare", "saxophone", "batterie",
    # metier/role
    "musicien", "musiciens", "chanteur", "chanteuse", "danseur", "danseuse", "danseurs",
    "soliste", "choriste", "chorale", "dj", "rappeur", "artiste",
    # personnage / regroupement de personnes
    "couple", "foule", "groupe",
]


def _audio(duration=100.0, sections=None):
    return AudioFeatures(duration=duration, tempo_bpm=100.0, sections=sections or [])


def _word_hits(text: str, nouns: list[str]) -> list[str]:
    normalized = text.lower()
    return [noun for noun in nouns if re.search(rf"\b{re.escape(noun)}\b", normalized)]


def test_no_genre_aesthetic_text_contains_a_forbidden_narrative_noun():
    for genre, text in GENRE_STAGING.items():
        hits = _word_hits(text, FORBIDDEN_NARRATIVE_NOUNS)
        assert not hits, f"GENRE_STAGING[{genre!r}] leaks narrative content: {hits} in {text!r}"


def test_two_different_genres_change_aesthetics_but_not_casting_decor_or_narrative():
    lyrics = (
        "Tu es partie loin de moi\n\n"
        "Je pense a toi tous les jours\n\n"
        "Ton absence me pese encore"
    )
    director = DirectorSettings(decor="plage")
    audio = _audio()

    dna_blues = build_project_dna(audio, genre="blues", director=director, lyrics_text=lyrics, project_id="same-id")
    dna_electro = build_project_dna(audio, genre="electro", director=director, lyrics_text=lyrics, project_id="same-id")

    # Aesthetics DID change.
    assert dna_blues.style.genre_staging_base != dna_electro.style.genre_staging_base

    # Everything narrative did NOT change.
    assert dna_blues.characters == dna_electro.characters
    assert dna_blues.referenced_presences == dna_electro.referenced_presences
    assert dna_blues.narrative.synopsis == dna_electro.narrative.synopsis
    assert dna_blues.narrative.mood_progression == dna_electro.narrative.mood_progression
    assert dna_blues.style.decor_family == dna_electro.style.decor_family == director.decor_phrase()


def test_two_different_genres_produce_the_same_narrative_scenes_and_casting_per_scene():
    lyrics = (
        "Tu es partie loin de moi\n\n"
        "Je pense a toi tous les jours\n\n"
        "Nous dansions ensemble avant\n\n"
        "La foule nous regardait danser\n\n"
        "Ton absence me pese encore"
    )
    director = DirectorSettings()
    sections = [
        AudioSection(index=i, start=i * 10, end=(i + 1) * 10, energy=e, local_tempo_bpm=100.0)
        for i, e in enumerate(["calme", "energique", "energique", "modere", "calme"])
    ]
    audio = _audio(duration=50.0, sections=sections)

    dna_blues = build_project_dna(audio, genre="blues", director=director, lyrics_text=lyrics, project_id="same-id")
    dna_rock = build_project_dna(audio, genre="rock", director=director, lyrics_text=lyrics, project_id="same-id")

    storyboard_blues = build_storyboard_from_dna(dna_blues, sections, lyrics_text=lyrics)
    storyboard_rock = build_storyboard_from_dna(dna_rock, sections, lyrics_text=lyrics)

    # Same story structure regardless of genre: same number of scenes, same
    # boundaries, same narrative roles, same casting per scene.
    assert len(storyboard_blues.scenes) == len(storyboard_rock.scenes)
    for scene_blues, scene_rock in zip(storyboard_blues.scenes, storyboard_rock.scenes):
        assert scene_blues.start_seconds == scene_rock.start_seconds
        assert scene_blues.end_seconds == scene_rock.end_seconds
        assert scene_blues.role == scene_rock.role
        assert scene_blues.character_ids == scene_rock.character_ids
        assert scene_blues.mood == scene_rock.mood

    # But the actual shot prompts DID pick up the aesthetic difference.
    assert storyboard_blues.scenes[0].shots[0].image_prompt != storyboard_rock.scenes[0].shots[0].image_prompt


def test_swapping_genre_never_changes_the_decor_or_character_fragments_in_a_shot_prompt():
    # The place (DirectorSettings.decor) and the character description are
    # legitimately part of every prompt -- they just must not move when only
    # the genre changes. Isolate them by removing each genre's own
    # (deliberately distinct) aesthetic text and comparing what's left.
    lyrics = "Je marche seul ce soir\n\nJe continue sans peur"
    director = DirectorSettings(decor="nightclub")  # a decor that could plausibly overlap with a genre word, on purpose
    sections = [AudioSection(index=0, start=0, end=20, energy="calme", local_tempo_bpm=90.0)]
    audio = _audio(duration=20.0, sections=sections)

    remainders = {}
    for genre in GENRE_STAGING:
        dna = build_project_dna(audio, genre=genre, director=director, lyrics_text=lyrics)
        storyboard = build_storyboard_from_dna(dna, sections, lyrics_text=lyrics)
        prompt = storyboard.all_shots()[0].image_prompt
        assert GENRE_STAGING[genre] in prompt
        # Strip the aesthetic text and the "genre musical: X" label (naming
        # the genre is fine meta-info, not narrative content) before comparing.
        remainder = prompt.replace(GENRE_STAGING[genre], "").replace(f"genre musical: {genre}", "")
        remainders[genre] = remainder

    unique_remainders = set(remainders.values())
    assert len(unique_remainders) == 1, (
        "the non-genre part of the prompt (decor, character, mood, camera...) "
        f"differs across genres: {remainders}"
    )
