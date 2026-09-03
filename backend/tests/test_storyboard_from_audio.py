from app.audio_analysis import AudioFeatures, AudioSection
from app.director import DirectorSettings
from app.storyboard import build_storyboard_from_audio
from app.transcription import TranscribedLine, TranscriptionResult


def _audio(sections_spec):
    sections = [
        AudioSection(index=i, start=s, end=e, energy=energy, local_tempo_bpm=120.0)
        for i, (s, e, energy) in enumerate(sections_spec)
    ]
    return AudioFeatures(duration=sections[-1].end, tempo_bpm=120.0, sections=sections)


def test_mp3_only_no_lyrics_still_produces_a_full_storyboard():
    audio = _audio([(0.0, 10.0, "calme"), (10.0, 20.0, "energique"), (20.0, 30.0, "modere")])
    storyboard = build_storyboard_from_audio(audio, DirectorSettings(), genre="afrobeat")
    assert len(storyboard.scenes) == 3
    assert all(s.lyrics_excerpt == "" for s in storyboard.scenes)
    assert all(s.image_prompt for s in storyboard.scenes)


def test_scenes_span_the_real_song_duration_exactly():
    audio = _audio([(0.0, 12.5, "calme"), (12.5, 40.0, "energique")])
    storyboard = build_storyboard_from_audio(audio, DirectorSettings(), genre="jazz")
    assert storyboard.scenes[0].start_seconds == 0.0
    assert storyboard.scenes[-1].end_seconds == 40.0
    assert storyboard.scenes[0].end_seconds == storyboard.scenes[1].start_seconds == 12.5


def test_energetic_sections_are_flagged_as_highlights():
    audio = _audio([(0.0, 10.0, "calme"), (10.0, 20.0, "energique"), (20.0, 30.0, "calme")])
    storyboard = build_storyboard_from_audio(audio, DirectorSettings(), genre="pop")
    highlights = storyboard.highlight_scenes()
    assert len(highlights) == 1
    assert highlights[0].index == 1


def test_at_least_one_highlight_even_if_nothing_is_energetic():
    audio = _audio([(0.0, 10.0, "calme"), (10.0, 20.0, "modere")])
    storyboard = build_storyboard_from_audio(audio, DirectorSettings(), genre="pop")
    assert len(storyboard.highlight_scenes()) == 1


def test_transcription_lines_are_matched_to_the_section_they_fall_in():
    audio = _audio([(0.0, 10.0, "calme"), (10.0, 20.0, "energique")])
    transcription = TranscriptionResult(
        language="fr",
        lines=[
            TranscribedLine(start=1.0, end=3.0, text="Premiere ligne"),
            TranscribedLine(start=4.0, end=6.0, text="Deuxieme ligne"),
            TranscribedLine(start=12.0, end=14.0, text="Troisieme ligne"),
        ],
    )
    storyboard = build_storyboard_from_audio(audio, DirectorSettings(), genre="soul", transcription=transcription)
    assert "Premiere ligne" in storyboard.scenes[0].lyrics_excerpt
    assert "Deuxieme ligne" in storyboard.scenes[0].lyrics_excerpt
    assert "Troisieme ligne" in storyboard.scenes[1].lyrics_excerpt
    assert "Troisieme" not in storyboard.scenes[0].lyrics_excerpt


def test_manual_lyrics_without_timing_are_distributed_across_sections():
    audio = _audio([(0.0, 10.0, "calme"), (10.0, 20.0, "energique"), (20.0, 30.0, "calme")])
    lyrics = "Bloc un\n\nBloc deux\n\nBloc trois"
    storyboard = build_storyboard_from_audio(audio, DirectorSettings(), genre="soul", lyrics_text=lyrics)
    excerpts = [s.lyrics_excerpt for s in storyboard.scenes]
    assert excerpts == ["Bloc un", "Bloc deux", "Bloc trois"]
