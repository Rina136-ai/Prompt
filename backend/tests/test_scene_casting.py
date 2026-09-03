"""Per-scene casting: the Project DNA is the film's global cast, never a
guarantee that every character appears in every scene. Selection is
story-driven (each scene's own text) and conservative (default to the
principal alone when nothing justifies more)."""
from app.audio_analysis import AudioSection
from app.director import DirectorSettings
from app.project_dna import build_project_dna
from app.storyboard import build_storyboard_from_dna
from app.audio_analysis import AudioFeatures


def _sections(specs):
    return [
        AudioSection(index=i, start=s, end=e, energy=energy, local_tempo_bpm=120.0)
        for i, (s, e, energy) in enumerate(specs)
    ]


def _principal_id(dna):
    return next(c.id for c in dna.characters if c.role == "narrateur_principal")


def _secondary_id(dna):
    return next(c.id for c in dna.characters if c.role == "figure_secondaire")


def test_principal_character_is_present_whenever_needed():
    # Solo narration throughout: only the principal exists, and it must be
    # in every scene since there's never a reason to drop the narrator.
    lyrics = "Je marche seul ce soir\n\nJe pense a mon chemin\n\nJe continue sans peur"
    audio = AudioFeatures(duration=30.0, tempo_bpm=110.0, sections=[])
    dna = build_project_dna(audio, genre="soul", director=DirectorSettings(), lyrics_text=lyrics)
    sections = _sections([(0, 10, "calme"), (10, 20, "modere"), (20, 30, "calme")])

    storyboard = build_storyboard_from_dna(dna, sections, lyrics_text=lyrics)

    principal_id = _principal_id(dna)
    for scene in storyboard.scenes:
        assert principal_id in scene.character_ids
        for shot in scene.shots:
            assert principal_id in shot.character_ids


def test_secondary_character_absent_where_nothing_justifies_it():
    # The song as a whole earns a figure_secondaire (recurring "tu"), but one
    # specific window (an instrumental-feeling bridge with no such mention)
    # should NOT include them.
    lyrics = (
        "Tu es partie loin de moi\n\n"
        "Je pense a toi tous les jours\n\n"
        "Ton absence me pese encore\n\n"
        "La pluie tombe sur la ville endormie\n\n"  # <- no duo marker: a neutral, character-free bridge
        "Le vent souffle sur les toits gris"
    )
    audio = AudioFeatures(duration=50.0, tempo_bpm=90.0, sections=[])
    dna = build_project_dna(audio, genre="soul", director=DirectorSettings(), lyrics_text=lyrics)
    assert any(c.role == "figure_secondaire" for c in dna.characters)  # sanity: DNA does grant them a global cast slot

    sections = _sections([(0, 10, "calme"), (10, 20, "calme"), (20, 30, "calme"), (30, 40, "energique"), (40, 50, "energique")])
    storyboard = build_storyboard_from_dna(dna, sections, lyrics_text=lyrics)

    secondary_id = _secondary_id(dna)
    scenes_with_secondary = [s for s in storyboard.scenes if secondary_id in s.character_ids]
    scenes_without_secondary = [s for s in storyboard.scenes if secondary_id not in s.character_ids]

    assert scenes_with_secondary, "should still appear where the lyrics justify it"
    assert scenes_without_secondary, "must NOT appear in every scene just because the DNA lists them"


def test_progressive_introduction_of_a_character_is_possible():
    # figure_secondaire is only textually present in the second half of the song.
    lyrics = (
        "Je marche seul dans la ville\n\n"
        "Personne a mes cotes ce matin\n\n"
        "Puis tu es arrivee dans ma vie\n\n"
        "Depuis je pense a toi sans cesse"
    )
    audio = AudioFeatures(duration=40.0, tempo_bpm=100.0, sections=[])
    dna = build_project_dna(audio, genre="pop", director=DirectorSettings(), lyrics_text=lyrics)
    sections = _sections([(0, 10, "calme"), (10, 20, "calme"), (20, 30, "modere"), (30, 40, "modere")])

    storyboard = build_storyboard_from_dna(dna, sections, lyrics_text=lyrics)
    secondary_id = _secondary_id(dna)

    first_half_has_secondary = any(secondary_id in s.character_ids for s in storyboard.scenes[: len(storyboard.scenes) // 2])
    second_half_has_secondary = any(secondary_id in s.character_ids for s in storyboard.scenes[len(storyboard.scenes) // 2 :])

    assert not first_half_has_secondary
    assert second_half_has_secondary


def test_abstract_spiritual_presence_never_becomes_a_visible_character_in_any_scene():
    lyrics = (
        "Toi, mon Dieu, guide mes pas\n\n"
        "Je prie le ciel chaque jour pour toi\n\n"
        "Ta lumiere est mon seul refuge"
    )
    audio = AudioFeatures(duration=30.0, tempo_bpm=80.0, sections=[])
    dna = build_project_dna(audio, genre="gospel", director=DirectorSettings(), lyrics_text=lyrics)
    assert all(c.role != "figure_secondaire" for c in dna.characters)  # not even granted a global cast slot

    sections = _sections([(0, 15, "calme"), (15, 30, "calme")])
    storyboard = build_storyboard_from_dna(dna, sections, lyrics_text=lyrics)

    all_ids_used = {cid for scene in storyboard.scenes for cid in scene.character_ids}
    assert all_ids_used == {_principal_id(dna)}


def test_global_cast_is_identical_between_a_preview_window_and_the_full_storyboard():
    lyrics = (
        "Tu es partie loin de moi\n\n"
        "Je pense a toi tous les jours\n\n"
        "Nous dansions ensemble avant\n\n"
        "La foule nous regardait danser\n\n"
        "Ton absence me pese encore"
    )
    audio = AudioFeatures(duration=50.0, tempo_bpm=100.0, sections=[])
    dna = build_project_dna(audio, genre="pop", director=DirectorSettings(), lyrics_text=lyrics)
    sections = _sections([(0, 10, "calme"), (10, 20, "energique"), (20, 30, "energique"), (30, 40, "modere"), (40, 50, "calme")])

    storyboard = build_storyboard_from_dna(dna, sections, lyrics_text=lyrics)
    cast_before = {c.id for c in dna.characters}

    # Simulate "preview then full": build the same storyboard again from the
    # SAME dna object, as render_shots does for /preview then /full.
    storyboard_again = build_storyboard_from_dna(dna, sections, lyrics_text=lyrics)
    cast_after = {c.id for c in dna.characters}

    assert cast_before == cast_after  # build_storyboard_from_dna never mutates the DNA's global cast
    assert [s.character_ids for s in storyboard.scenes] == [s.character_ids for s in storyboard_again.scenes]
