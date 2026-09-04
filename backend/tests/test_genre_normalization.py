"""Regression tests for correction #2: every genre value produced by the
real classifier or its BPM/energy fallback must resolve to a valid
GENRE_STAGING entry -- generic for any genre string, not tuned to one song."""
from app.audio_analysis import AudioFeatures, AudioSection
from app.director import DirectorSettings
from app.project_dna import build_project_dna
from app.storyboard import DEFAULT_GENRE_KEY, GENRE_STAGING, normalize_genre_key


def test_exact_genre_staging_key_is_returned_unchanged():
    for key in GENRE_STAGING:
        assert normalize_genre_key(key) == key
        assert normalize_genre_key(key.upper()) == key


def test_every_bpm_energy_fallback_label_normalizes_to_a_valid_key():
    # The exact composite strings AudioFeatures.suggested_genre_family() can
    # produce -- every one of them must resolve to a real GENRE_STAGING key.
    fallback_labels = ["afrobeat_amapiano_dance", "soul_gospel_ballade", "jazz_rnb_zouk", "pop_rock"]
    for label in fallback_labels:
        normalized = normalize_genre_key(label)
        assert normalized in GENRE_STAGING, f"{label!r} -> {normalized!r} is not a valid GENRE_STAGING key"


def test_completely_unknown_genre_string_falls_back_to_the_default_key():
    assert normalize_genre_key("chill-lofi") == DEFAULT_GENRE_KEY
    assert normalize_genre_key("") == DEFAULT_GENRE_KEY
    assert normalize_genre_key("   ") == DEFAULT_GENRE_KEY


def test_suggested_genre_family_output_always_normalizes_generically():
    # End-to-end, generic: whatever suggested_genre_family() computes for
    # ANY audio profile, normalize_genre_key must accept it.
    for tempo, energies in [
        (130, ["energique"] * 4),
        (70, ["calme"] * 4),
        (100, ["modere"] * 4),
        (140, ["calme"] * 4),
    ]:
        sections = [
            AudioSection(index=i, start=i * 10, end=(i + 1) * 10, energy=e, local_tempo_bpm=tempo)
            for i, e in enumerate(energies)
        ]
        features = AudioFeatures(duration=40.0, tempo_bpm=tempo, sections=sections)
        label = features.suggested_genre_family()
        assert normalize_genre_key(label) in GENRE_STAGING


def test_project_dna_style_bible_is_never_empty_for_an_unrecognized_genre():
    audio = AudioFeatures(duration=30.0, tempo_bpm=100.0, sections=[])
    dna = build_project_dna(audio, genre="jazz_rnb_zouk", director=DirectorSettings())
    assert dna.style.genre_staging_base  # not empty
    assert dna.style.genre_staging_base == GENRE_STAGING["jazz"]
