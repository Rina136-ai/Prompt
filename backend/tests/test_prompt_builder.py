from app.director import DirectorSettings
from app.prompt_builder import build_scene_prompt, build_video_motion_prompt


def test_build_scene_prompt_includes_all_facets():
    director = DirectorSettings(
        characters="africains", style="photorealiste", dance="afrobeat",
        era="contemporaine", decor="afrique", camera="cinematographique",
    )
    prompt = build_scene_prompt(
        scene_description="des danseurs dans un village",
        mood="joie",
        genre="afrobeat",
        director=director,
        energy="energique",
        is_chorus=True,
    )
    assert "des danseurs dans un village" in prompt
    assert "genre musical: afrobeat" in prompt
    assert "ambiance: joie" in prompt
    assert "danseurs et personnages africains" in prompt
    assert "photorealiste" in prompt
    assert "chorégraphie afrobeat" in prompt
    assert "moment fort du refrain" in prompt


def test_custom_characters_and_decor_are_used_verbatim():
    director = DirectorSettings(
        characters="personnalise", characters_custom="un vieil homme sage",
        decor="personnalise", decor_custom="un desert au crepuscule",
    )
    prompt = build_scene_prompt(scene_description="x", mood="nostalgie", genre="soul", director=director)
    assert "un vieil homme sage" in prompt
    assert "un desert au crepuscule" in prompt


def test_video_motion_prompt_wraps_scene_prompt_with_camera():
    motion = build_video_motion_prompt("scene de base", camera="drone")
    assert motion.startswith("scene de base,")
    assert "camera:" in motion
