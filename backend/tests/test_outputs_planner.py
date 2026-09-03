from app.director import DirectorSettings
from app.outputs_planner import SHORT_MAX_SECONDS, plan_outputs
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


def _storyboard():
    return build_storyboard(LYRICS, DirectorSettings(), genre="afrobeat")


def test_main_clip_covers_every_scene():
    storyboard = _storyboard()
    plan = plan_outputs(storyboard)
    assert plan.main_clip_scene_indices == [s.index for s in storyboard.scenes]


def test_shorts_are_built_around_highlight_scenes():
    storyboard = _storyboard()
    plan = plan_outputs(storyboard)
    assert 1 <= len(plan.shorts) <= 3
    for short in plan.shorts:
        assert short.approx_seconds <= SHORT_MAX_SECONDS
        assert short.scene_indices == sorted(short.scene_indices)


def test_lyric_video_and_images_cover_all_scenes():
    storyboard = _storyboard()
    plan = plan_outputs(storyboard)
    assert plan.lyric_video_scene_indices == plan.main_clip_scene_indices
    assert plan.image_scene_indices == plan.main_clip_scene_indices


def test_three_variants_are_planned():
    storyboard = _storyboard()
    plan = plan_outputs(storyboard)
    assert len(plan.variants) == 3
    assert plan.variants[0].style_override == ""
