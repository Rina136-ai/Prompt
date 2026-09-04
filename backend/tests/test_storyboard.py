from app.director import DirectorSettings
from app.storyboard import build_storyboard

LYRICS = """Petit matin, le soleil se leve
Le village s'eveille doucement

On danse, on chante, on vibre ensemble
Le rythme nous rend libres

Je me souviens des tambours d'hier
Quand grand-mere chantait pour nous

On danse, on chante, on vibre ensemble
Le rythme nous rend libres

Ce soir encore, la fete continue"""


def test_storyboard_has_one_scene_per_section():
    storyboard = build_storyboard(LYRICS, DirectorSettings(), genre="afrobeat")
    assert len(storyboard.scenes) == 5
    assert storyboard.genre == "afrobeat"


def test_chorus_sections_are_highlights():
    storyboard = build_storyboard(LYRICS, DirectorSettings(), genre="afrobeat")
    highlights = storyboard.highlight_scenes()
    assert len(highlights) == 2
    assert all(s.is_highlight for s in highlights)


def test_scene_prompt_includes_genre_staging_and_director_settings():
    director = DirectorSettings(style="photorealiste", camera="drone")
    storyboard = build_storyboard(LYRICS, director, genre="afrobeat")
    prompt = storyboard.scenes[0].image_prompt
    assert "afrobeat" in prompt
    assert "photorealiste" in prompt
    assert "montage" in prompt  # aesthetic descriptor from GENRE_STAGING["afrobeat"], not a narrative noun


def test_video_prompt_references_camera_choice():
    director = DirectorSettings(camera="drone")
    storyboard = build_storyboard(LYRICS, director, genre="jazz")
    assert "drone" in storyboard.scenes[0].video_prompt.lower() or "aerienne" in storyboard.scenes[0].video_prompt.lower()


def test_unknown_genre_falls_back_to_a_valid_staging_not_an_empty_one():
    # Regression: an unrecognized genre string must still resolve to a real,
    # non-empty GENRE_STAGING entry (normalize_genre_key -> DEFAULT_GENRE_KEY),
    # not the fully generic prose fallback.
    storyboard = build_storyboard(LYRICS, DirectorSettings(), genre="chill-lofi")
    from app.storyboard import DEFAULT_GENRE_KEY, GENRE_STAGING

    assert GENRE_STAGING[DEFAULT_GENRE_KEY] in storyboard.scenes[0].image_prompt
