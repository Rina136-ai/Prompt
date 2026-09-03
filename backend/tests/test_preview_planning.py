from app.outputs_planner import PREVIEW_MAX_SECONDS, PREVIEW_MIN_SECONDS, plan_preview
from app.storyboard import NarrativeScene, NarrativeStoryboard, Shot


def _scene(index, start, end, energy, role, is_chorus_scene, narrative_importance_score, emotion_score):
    shot = Shot(index=index, start_seconds=start, end_seconds=end, character_ids=["figure_principale"], image_prompt="p", video_prompt="v")
    return NarrativeScene(
        index=index, role=role, start_seconds=start, end_seconds=end, energy=energy, mood="joie",
        is_chorus_scene=is_chorus_scene, narrative_importance_score=narrative_importance_score,
        emotion_score=emotion_score, character_ids=["figure_principale"], shots=[shot],
    )


def test_preview_picks_the_chorus_not_the_raw_energy_peak():
    # Scene 1 is the single most energetic passage, but it's a throwaway
    # transition: low narrative importance, no chorus, low emotion.
    # Scene 2 is a genuine refrain: moderately energetic but high narrative
    # importance + chorus bonus + real emotion -- it should win.
    scenes = [
        _scene(0, 0, 10, energy="calme", role="introduction", is_chorus_scene=False, narrative_importance_score=0.3, emotion_score=0.2),
        _scene(1, 10, 20, energy="energique", role="couplet", is_chorus_scene=False, narrative_importance_score=0.3, emotion_score=0.1),
        _scene(2, 20, 30, energy="modere", role="refrain", is_chorus_scene=True, narrative_importance_score=1.0, emotion_score=0.9),
        _scene(3, 30, 40, energy="calme", role="conclusion", is_chorus_scene=False, narrative_importance_score=0.3, emotion_score=0.2),
    ]
    storyboard = NarrativeStoryboard(dna_id="x", genre="pop", scenes=scenes)

    plan = plan_preview(storyboard, target_seconds=10, min_seconds=8, max_seconds=12)

    assert 2 in plan.scene_indices
    assert 1 not in plan.scene_indices  # the raw energy peak, correctly NOT chosen alone


def test_preview_duration_within_target_bounds_when_possible():
    scenes = [_scene(i, i * 8, i * 8 + 8, "modere", "couplet", False, 0.5, 0.3) for i in range(6)]
    storyboard = NarrativeStoryboard(dna_id="x", genre="pop", scenes=scenes)
    plan = plan_preview(storyboard)
    assert PREVIEW_MIN_SECONDS <= plan.approx_seconds <= PREVIEW_MAX_SECONDS


def test_preview_returns_contiguous_scene_window():
    scenes = [_scene(i, i * 8, i * 8 + 8, "modere", "couplet", i == 3, 0.5, 0.3) for i in range(6)]
    storyboard = NarrativeStoryboard(dna_id="x", genre="pop", scenes=scenes)
    plan = plan_preview(storyboard)
    indices = plan.scene_indices
    assert indices == list(range(min(indices), max(indices) + 1))


def test_very_short_song_falls_back_to_closest_available_window():
    scenes = [_scene(0, 0, 5, "calme", "introduction", False, 0.3, 0.2)]
    storyboard = NarrativeStoryboard(dna_id="x", genre="pop", scenes=scenes)
    plan = plan_preview(storyboard)
    assert plan.scene_indices == [0]
    assert plan.approx_seconds == 5.0


def test_empty_storyboard_returns_an_empty_preview():
    storyboard = NarrativeStoryboard(dna_id="x", genre="pop", scenes=[])
    plan = plan_preview(storyboard)
    assert plan.shot_indices == []
    assert plan.approx_seconds == 0.0
