"""Regression for correction #3: a sustained energetic plateau must not be
labeled a generic 'couplet' just because energy stopped rising -- it needs
its own role, based on absolute level + trajectory, generic for any song."""
from app.audio_analysis import AudioSection
from app.director import DirectorSettings
from app.project_dna import build_project_dna
from app.storyboard import NARRATIVE_IMPORTANCE, _assign_role, build_storyboard_from_dna
from app.audio_analysis import AudioFeatures


def test_assign_role_labels_a_sustained_energetic_plateau_as_pic_soutenu():
    # energy stays "energique" from one scene to the next -> not a "montee"
    # (nothing is rising anymore) and not a generic "couplet" either.
    role = _assign_role(group_index=2, total_groups=5, is_chorus_scene=False, energy_now="energique", energy_prev="energique")
    assert role == "pic_soutenu"


def test_assign_role_still_labels_a_genuine_rise_as_montee():
    role = _assign_role(group_index=2, total_groups=5, is_chorus_scene=False, energy_now="energique", energy_prev="modere")
    assert role == "montee"


def test_assign_role_does_not_mislabel_a_sustained_calm_or_moderate_plateau():
    # The rule targets a sustained PEAK specifically (absolute top level),
    # not any repeated energy level.
    assert _assign_role(2, 5, False, "calme", "calme") == "couplet"
    assert _assign_role(2, 5, False, "modere", "modere") == "couplet"


def test_pic_soutenu_has_higher_narrative_importance_than_a_generic_couplet():
    assert NARRATIVE_IMPORTANCE["pic_soutenu"] > NARRATIVE_IMPORTANCE["couplet"]


def test_end_to_end_two_consecutive_energetic_sections_yield_a_sustained_peak_scene():
    # Generic reproduction of the real-song finding (Et-moi-Seigneur.mp3 had
    # two back-to-back "energique" sections mislabeled "couplet") -- built
    # here from a synthetic, unrelated audio profile to prove the fix is not
    # tuned to that one song.
    audio = AudioFeatures(duration=60.0, tempo_bpm=100.0, sections=[])
    dna = build_project_dna(audio, genre="pop", director=DirectorSettings())
    sections = [
        AudioSection(index=0, start=0, end=15, energy="calme", local_tempo_bpm=100.0),
        AudioSection(index=1, start=15, end=30, energy="energique", local_tempo_bpm=100.0),
        AudioSection(index=2, start=30, end=45, energy="energique", local_tempo_bpm=100.0),
        AudioSection(index=3, start=45, end=60, energy="calme", local_tempo_bpm=100.0),
    ]
    storyboard = build_storyboard_from_dna(dna, sections)

    roles = [s.role for s in storyboard.scenes]
    # The scene right after the rise (still at peak energy) must be
    # "pic_soutenu", not a generic "couplet".
    montee_index = roles.index("montee")
    assert roles[montee_index + 1] == "pic_soutenu"
