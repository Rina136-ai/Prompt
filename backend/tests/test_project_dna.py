from app.audio_analysis import AudioFeatures, AudioSection
from app.director import DirectorSettings
from app.project_dna import build_project_dna, load_project_dna, persist_project_dna
from app.transcription import TranscribedLine, TranscriptionResult


def _audio(duration=60.0, tempo=120.0):
    return AudioFeatures(
        duration=duration,
        tempo_bpm=tempo,
        sections=[AudioSection(index=0, start=0.0, end=duration, energy="modere", local_tempo_bpm=tempo)],
    )


def test_no_lyrics_gives_a_single_minimal_character_regardless_of_genre():
    dna_afrobeat = build_project_dna(_audio(), genre="afrobeat", director=DirectorSettings())
    dna_gospel = build_project_dna(_audio(), genre="gospel", director=DirectorSettings())
    assert [c.role for c in dna_afrobeat.characters] == ["narrateur_principal"]
    assert [c.role for c in dna_gospel.characters] == ["narrateur_principal"]


def test_genre_never_adds_dancers_or_choir_by_itself():
    # Correction #2: afrobeat does not imply dancers, gospel does not imply a choir,
    # unless the lyrics actually say so.
    dna = build_project_dna(_audio(), genre="afrobeat", director=DirectorSettings(), lyrics_text="Je marche seul\n\nJe pense a mon chemin")
    roles = {c.role for c in dna.characters}
    assert "groupe" not in roles
    assert "figure_secondaire" not in roles


def test_recurring_duo_in_lyrics_adds_a_second_character():
    lyrics = "Tu es partie loin de moi\n\nJe pense a toi tous les jours\n\nTon absence me pese"
    dna = build_project_dna(_audio(), genre="soul", director=DirectorSettings(), lyrics_text=lyrics)
    roles = {c.role for c in dna.characters}
    assert "figure_secondaire" in roles


def test_god_addressed_as_tu_does_not_become_a_character():
    lyrics = "Toi, mon Dieu, guide mes pas\n\nJe prie le ciel pour toi"
    dna = build_project_dna(_audio(), genre="gospel", director=DirectorSettings(), lyrics_text=lyrics)
    roles = {c.role for c in dna.characters}
    assert "figure_secondaire" not in roles
    assert any(rp.reason.startswith("reference probablement abstraite") for rp in dna.referenced_presences)


def test_recurring_collective_address_adds_a_group_character():
    lyrics = "Nous dansons tous ensemble\n\nLa foule vibre avec nous\n\nOn est ensemble ce soir"
    dna = build_project_dna(_audio(), genre="pop", director=DirectorSettings(), lyrics_text=lyrics)
    roles = {c.role for c in dna.characters}
    assert "groupe" in roles


def test_transcription_feeds_the_narrative_arc_when_no_manual_lyrics():
    transcription = TranscriptionResult(
        language="fr",
        lines=[TranscribedLine(start=0, end=2, text="On danse ensemble ce soir")],
    )
    dna = build_project_dna(_audio(), genre="afrobeat", director=DirectorSettings(), transcription=transcription)
    assert dna.narrative.mood_progression  # not the instrumental fallback synopsis
    assert "instrumental" not in dna.narrative.synopsis.lower()


def test_style_bible_carries_genre_aesthetics_not_narrative_content():
    # Correction: genre must color HOW a scene is shot (editing/camera/light/
    # movement quality), never WHO is in it or WHERE it happens.
    dna = build_project_dna(_audio(), genre="afrobeat", director=DirectorSettings())
    assert "montage" in dna.style.genre_staging_base or "mouvements" in dna.style.genre_staging_base
    assert all(c.role != "danseurs" for c in dna.characters)  # never a casting signal
    forbidden_nouns = ["danseur", "danseuse", "chanteur", "chanteuse", "musicien", "bar", "club", "rue", "scene de concert"]
    assert not any(noun in dna.style.genre_staging_base.lower() for noun in forbidden_nouns)


def test_json_round_trip_preserves_everything(tmp_path):
    lyrics = "Tu es partie loin de moi\n\nJe pense a toi tous les jours\n\nTon absence me pese"
    dna = build_project_dna(_audio(), genre="soul", director=DirectorSettings(), lyrics_text=lyrics)
    path = str(tmp_path / "dna.json")
    persist_project_dna(dna, path)
    reloaded = load_project_dna(path)
    assert reloaded == dna
