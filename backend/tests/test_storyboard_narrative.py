from app.audio_analysis import AudioSection
from app.director import DirectorSettings
from app.project_dna import build_project_dna
from app.storyboard import (
    MAX_SHOT_SECONDS,
    MIN_SHOT_SECONDS,
    NarrativeStoryboard,
    build_storyboard_from_dna,
    plan_shots_for_scene,
)
from app.audio_analysis import AudioFeatures


def _sections(specs):
    return [
        AudioSection(index=i, start=s, end=e, energy=energy, local_tempo_bpm=120.0)
        for i, (s, e, energy) in enumerate(specs)
    ]


def _dna(genre="pop", lyrics_text=None):
    audio = AudioFeatures(duration=100.0, tempo_bpm=120.0, sections=[])
    return build_project_dna(audio, genre=genre, director=DirectorSettings(), lyrics_text=lyrics_text)


# --- plan_shots_for_scene: correction #1 (no mechanical 1 section = 1 shot) ---

def test_shot_count_is_not_tied_to_a_fixed_number():
    calm_long = plan_shots_for_scene(0.0, 24.0, energy="calme", role="pont")
    energetic_short = plan_shots_for_scene(0.0, 12.0, energy="energique", role="refrain")
    # A calm, long, low-importance scene should NOT automatically get more shots
    # than a short energetic refrain -- editing rhythm decides, not raw duration alone.
    assert len(calm_long) <= 3
    assert len(energetic_short) >= 2


def test_energetic_refrain_gets_shorter_shots_than_calm_intro_of_same_duration():
    refrain_shots = plan_shots_for_scene(0.0, 20.0, energy="energique", role="refrain")
    intro_shots = plan_shots_for_scene(0.0, 20.0, energy="calme", role="introduction")
    avg_refrain = sum(e - s for s, e in refrain_shots) / len(refrain_shots)
    avg_intro = sum(e - s for s, e in intro_shots) / len(intro_shots)
    assert avg_refrain < avg_intro


def test_shots_respect_min_and_max_duration_bounds():
    for shots in [
        plan_shots_for_scene(0.0, 5.0, energy="energique", role="refrain"),
        plan_shots_for_scene(0.0, 40.0, energy="calme", role="pont"),
    ]:
        for start, end in shots:
            assert (end - start) >= MIN_SHOT_SECONDS - 0.01 or len(shots) == 1
            assert (end - start) <= MAX_SHOT_SECONDS + 0.01


def test_boundary_hints_only_nudge_cuts_never_change_shot_count():
    without_hints = plan_shots_for_scene(0.0, 20.0, energy="modere", role="couplet")
    with_hints = plan_shots_for_scene(0.0, 20.0, energy="modere", role="couplet", boundary_hints=[6.8, 13.5])
    assert len(without_hints) == len(with_hints)


def test_single_section_scene_still_gets_a_valid_shot_plan():
    shots = plan_shots_for_scene(10.0, 12.0, energy="calme", role="introduction")
    assert shots[0][0] == 10.0
    assert shots[-1][1] == 12.0


# --- build_storyboard_from_dna: sections group into scenes, scenes decompose into shots ---

def test_a_scene_can_span_several_audio_sections():
    dna = _dna()
    sections = _sections([(0, 8, "calme"), (8, 16, "calme"), (16, 24, "calme")])
    storyboard = build_storyboard_from_dna(dna, sections)
    # three same-mood/same-repetition sections should merge into fewer scenes than sections
    assert len(storyboard.scenes) < len(sections)


def test_all_shots_cover_the_full_real_duration_contiguously():
    dna = _dna()
    sections = _sections([(0, 10, "calme"), (10, 22, "energique"), (22, 40, "calme")])
    storyboard = build_storyboard_from_dna(dna, sections)
    shots = storyboard.all_shots()
    assert shots[0].start_seconds == 0.0
    assert shots[-1].end_seconds == 40.0
    for a, b in zip(shots, shots[1:]):
        assert a.end_seconds == b.start_seconds


def test_first_and_last_scenes_get_introduction_and_conclusion_roles():
    dna = _dna()
    sections = _sections([(0, 8, "calme"), (8, 16, "energique"), (16, 24, "calme")])
    storyboard = build_storyboard_from_dna(dna, sections)
    assert storyboard.scenes[0].role == "introduction"
    assert storyboard.scenes[-1].role == "conclusion"


def test_repeated_excerpt_is_marked_as_a_chorus_scene():
    dna = _dna()
    sections = _sections([(0, 8, "modere"), (8, 16, "energique"), (16, 24, "modere"), (24, 32, "energique")])
    lyrics = "On danse toute la nuit\n\nRefrain repete plusieurs fois\n\nOn danse toute la nuit\n\nRefrain repete plusieurs fois"
    storyboard = build_storyboard_from_dna(dna, sections, lyrics_text=lyrics)
    assert any(scene.is_chorus_scene for scene in storyboard.scenes)


def test_every_shot_carries_the_dna_characters():
    lyrics = "Tu es partie loin de moi\n\nJe pense a toi tous les jours\n\nTon absence me pese"
    dna = _dna(genre="soul", lyrics_text=lyrics)
    sections = _sections([(0, 15, "calme"), (15, 30, "modere")])
    storyboard = build_storyboard_from_dna(dna, sections, lyrics_text=lyrics)
    character_ids = {c.id for c in dna.characters}
    for shot in storyboard.all_shots():
        assert set(shot.character_ids) == character_ids


def test_no_audio_sections_returns_an_empty_storyboard_without_crashing():
    dna = _dna()
    storyboard = build_storyboard_from_dna(dna, [])
    assert isinstance(storyboard, NarrativeStoryboard)
    assert storyboard.scenes == []
