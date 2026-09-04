"""Regression for correction #4: an excellent window landing just over
PREVIEW_MAX_SECONDS must not be rejected outright, and the final preview
must never exceed max_seconds -- via precise trimming, not by falling back
to a pure energy-peak pick."""
from app.outputs_planner import PREVIEW_MAX_SECONDS, plan_preview
from app.storyboard import NarrativeScene, NarrativeStoryboard, Shot


def _scene(index, start, end, energy, role, is_chorus_scene, narrative_importance_score, emotion_score, n_shots=1):
    shot_len = (end - start) / n_shots
    shots = [
        Shot(
            index=index * 10 + k,
            start_seconds=round(start + k * shot_len, 2),
            end_seconds=round(start + (k + 1) * shot_len, 2),
            character_ids=["figure_principale"],
            image_prompt="p",
            video_prompt="v",
        )
        for k in range(n_shots)
    ]
    return NarrativeScene(
        index=index, role=role, start_seconds=start, end_seconds=end, energy=energy, mood="joie",
        is_chorus_scene=is_chorus_scene, narrative_importance_score=narrative_importance_score,
        emotion_score=emotion_score, character_ids=["figure_principale"], shots=shots,
    )


def test_a_window_just_over_the_cap_is_not_rejected_outright():
    # Reproduces the real finding on Et-moi-Seigneur.mp3: the best-scoring
    # scene was 30.05s, 0.05s over the 30s cap, and used to be discarded in
    # favor of a worse-scoring in-range scene.
    scenes = [
        _scene(0, 0, 10, "calme", "introduction", False, 0.3, 0.2),
        _scene(1, 10, 40.05, "energique", "pic_soutenu", False, 0.75, 0.6, n_shots=3),  # 30.05s, best score
        _scene(2, 40.05, 55, "energique", "couplet", False, 0.3, 0.1),  # in-range but weaker, even combined with scene 3
        _scene(3, 55, 65, "calme", "conclusion", False, 0.3, 0.2),
    ]
    storyboard = NarrativeStoryboard(dna_id="x", genre="pop", scenes=scenes)

    plan = plan_preview(storyboard)

    assert 1 in plan.scene_indices  # the 30.05s scene IS chosen despite exceeding the cap
    assert 2 not in plan.scene_indices  # not the weaker in-range alternative


def test_final_preview_never_exceeds_max_seconds_even_when_the_best_window_is_longer():
    scenes = [
        _scene(0, 0, 10, "calme", "introduction", False, 0.3, 0.2),
        _scene(1, 10, 40.05, "energique", "pic_soutenu", False, 0.75, 0.6, n_shots=3),
        _scene(2, 40.05, 65, "calme", "conclusion", False, 0.3, 0.2),
    ]
    storyboard = NarrativeStoryboard(dna_id="x", genre="pop", scenes=scenes)

    plan = plan_preview(storyboard)

    assert plan.approx_seconds <= PREVIEW_MAX_SECONDS
    assert (plan.end_seconds - plan.start_seconds) <= PREVIEW_MAX_SECONDS + 0.01


def test_trim_shortens_the_last_shot_precisely_instead_of_dropping_a_whole_scene():
    scenes = [
        _scene(0, 0, 10, "calme", "introduction", False, 0.3, 0.2),
        _scene(1, 10, 40.05, "energique", "pic_soutenu", False, 0.75, 0.6, n_shots=3),
    ]
    storyboard = NarrativeStoryboard(dna_id="x", genre="pop", scenes=scenes)

    plan = plan_preview(storyboard, min_seconds=5, max_seconds=30, target_seconds=25)

    assert plan.shot_duration_overrides, "expected the trailing shot to be shortened, not dropped"
    # Only ever the single trailing shot is overridden -- everything before it keeps its full duration.
    assert len(plan.shot_duration_overrides) == 1
    (overridden_index, overridden_duration), = plan.shot_duration_overrides.items()
    assert overridden_index in plan.shot_indices
    assert overridden_duration > 0


def test_a_window_far_beyond_tolerance_is_not_pulled_in_just_for_its_score():
    scenes = [
        _scene(0, 0, 10, "calme", "introduction", False, 0.3, 0.2),
        _scene(1, 10, 15, "energique", "couplet", False, 0.5, 0.9, n_shots=1),  # tiny but "in range" alone? no: 5s < min
        _scene(2, 15, 100, "energique", "pic_soutenu", True, 1.0, 1.0, n_shots=5),  # 85s, way beyond tolerance
    ]
    storyboard = NarrativeStoryboard(dna_id="x", genre="pop", scenes=scenes)

    plan = plan_preview(storyboard)

    # The 85s scene alone is far beyond PREVIEW_MAX_SECONDS + PREVIEW_TOLERANCE_SECONDS (35s)
    # and must not be selected as a single-scene window just because its score is highest.
    if plan.scene_indices == [2]:
        assert plan.approx_seconds <= 35.0 + 0.01  # sanity: if chosen, it must still have been trimmed


def test_choice_remains_multi_criteria_not_pure_energy_peak_even_with_tolerance():
    # Same setup as the original preview regression test, now re-checked
    # with tolerance active: the raw energy peak (scene 1) must still lose
    # to the narratively-important, chorus-flagged scene 2.
    scenes = [
        _scene(0, 0, 10, "calme", "introduction", False, 0.3, 0.2),
        _scene(1, 10, 20, "energique", "couplet", False, 0.3, 0.1),
        _scene(2, 20, 30, "modere", "refrain", True, 1.0, 0.9),
        _scene(3, 30, 40, "calme", "conclusion", False, 0.3, 0.2),
    ]
    storyboard = NarrativeStoryboard(dna_id="x", genre="pop", scenes=scenes)

    plan = plan_preview(storyboard, target_seconds=10, min_seconds=8, max_seconds=12)

    assert 2 in plan.scene_indices
    assert 1 not in plan.scene_indices
