"""Regression tests for round-2 targeted corrections, found via the real-file
test on Et-moi-Seigneur.mp3 (with lyrics). All three are generic fixes, not
specialized for that song:

1. The synopsis must reflect a real arc (where the text starts vs. where it
   ends) and its tensions (a secondary, contrasting mood), not just
   "dominant mood + N moments".
2. A weak, generic collective pronoun ("nous", "tous", "vous") recurring
   alone must never be enough to cast a visible group -- a group needs at
   least one unambiguous, strong cue of an actual gathered presence.
3. Narrative scene boundaries must not mechanically track lyric-sheet
   paragraph breaks: they follow the audio's own structure (energy +
   chorus repetition), identically whether or not lyrics are supplied.
"""
from app.audio_analysis import AudioFeatures, AudioSection
from app.director import DirectorSettings
from app.project_dna import build_project_dna
from app.storyboard import build_storyboard_from_dna


def _audio(duration=100.0, sections=None):
    return AudioFeatures(duration=duration, tempo_bpm=100.0, sections=sections or [])


# --- 1. Synopsis reflects a real arc + tension, not a bare statistic -------


def test_synopsis_names_the_opening_and_closing_mood_when_they_differ():
    # Starts joyful, ends sorrowful: a real arc, not the same mood throughout.
    lyrics = (
        "On danse et on rit sous le soleil\n\n"
        "La fete bat son plein ce soir\n\n"
        "Puis vient l'heure des adieux\n\n"
        "Je pleure seul, tu m'as quitte"
    )
    dna = build_project_dna(_audio(), genre="pop", director=DirectorSettings(), lyrics_text=lyrics)
    synopsis = dna.narrative.synopsis.lower()

    assert "joie" in synopsis and "tristesse" in synopsis
    # Not the old bare-statistic template.
    assert "humeur dominante" not in synopsis
    assert "trajectoire" in synopsis or "allant de" in synopsis


def test_synopsis_names_a_tension_between_two_recurring_moods():
    lyrics = (
        "Je pleure, seul, la nuit me manque\n\n"
        "On danse, on rit, la fete continue\n\n"
        "Encore des larmes que je cache\n\n"
        "Puis la musique me fait vibrer encore"
    )
    dna = build_project_dna(_audio(), genre="pop", director=DirectorSettings(), lyrics_text=lyrics)
    synopsis = dna.narrative.synopsis.lower()

    assert "tension" in synopsis


def test_synopsis_stays_generic_not_hardcoded_to_one_songs_wording():
    # Two different lyric sets, each with their own arc, must produce two
    # different synopses built from the same generic template -- no
    # song-specific branch anywhere in the synopsis logic.
    lyrics_a = "Je ris et je danse\n\nLa fete est belle\n\nJe pleure ce soir\n\nSeul dans le noir"
    lyrics_b = "Je me souviens d'hier\n\nL'enfance et le passe\n\nOn danse, on rit\n\nEnsemble ce soir"
    dna_a = build_project_dna(_audio(), genre="pop", director=DirectorSettings(), lyrics_text=lyrics_a)
    dna_b = build_project_dna(_audio(), genre="pop", director=DirectorSettings(), lyrics_text=lyrics_b)

    assert dna_a.narrative.synopsis != dna_b.narrative.synopsis
    assert "humeur dominante" not in dna_a.narrative.synopsis.lower()
    assert "humeur dominante" not in dna_b.narrative.synopsis.lower()


# --- 2. Weak collective pronouns alone never cast a visible group ----------


def test_weak_collective_pronoun_recurring_alone_never_casts_a_group():
    # "nous" and "tous" each recur across 2+ segments -- would have passed
    # the old occurrence-only threshold -- but neither segment contains any
    # unambiguous group cue (no "ensemble", "la foule", "on danse").
    lyrics = (
        "Pour tous les reves laisses de cote\n\n"
        "On nous dit forts, on nous croit sages\n\n"
        "Nous verrons bien ce que la vie reserve\n\n"
        "Merci pour tous ceux qui nous soutiennent"
    )
    dna = build_project_dna(_audio(), genre="soul", director=DirectorSettings(), lyrics_text=lyrics)
    roles = {c.role for c in dna.characters}

    assert "groupe" not in roles
    reasons = [rp.reason for rp in dna.referenced_presences]
    assert any("generique" in r or "generiques" in r for r in reasons)


def test_strong_collective_cue_still_casts_a_group_when_it_recurs():
    # The legitimate case must keep working: an unambiguous, recurring group
    # cue ("la foule", "ensemble") still earns a visible group.
    lyrics = (
        "La foule danse avec nous ce soir\n\n"
        "Nous marchons vers la sortie\n\n"
        "Tous ensemble on chante encore\n\n"
        "La nuit se termine tranquillement"
    )
    dna = build_project_dna(_audio(), genre="pop", director=DirectorSettings(), lyrics_text=lyrics)
    roles = {c.role for c in dna.characters}

    assert "groupe" in roles


def test_weak_collective_pronoun_never_added_to_a_scene_either():
    lyrics = (
        "Pour tous les reves laisses de cote\n\n"
        "On nous dit forts, on nous croit sages\n\n"
        "Nous verrons bien ce que la vie reserve\n\n"
        "Merci pour tous ceux qui nous soutiennent"
    )
    audio = AudioFeatures(duration=40.0, tempo_bpm=100.0, sections=[])
    dna = build_project_dna(audio, genre="soul", director=DirectorSettings(), lyrics_text=lyrics)
    sections = [
        AudioSection(index=i, start=i * 10, end=(i + 1) * 10, energy="calme", local_tempo_bpm=100.0)
        for i in range(4)
    ]
    storyboard = build_storyboard_from_dna(dna, sections, lyrics_text=lyrics)

    all_ids_used = {cid for scene in storyboard.scenes for cid in scene.character_ids}
    principal_id = next(c.id for c in dna.characters if c.role == "narrateur_principal")
    assert all_ids_used == {principal_id}


# --- 3. Scene boundaries follow audio structure, not lyric paragraph breaks -


def test_many_short_lyric_blocks_do_not_force_a_scene_per_block():
    # 8 short, blank-line-separated paragraphs, each with a different
    # dominant mood word so every block scores a different label -- the
    # exact condition that produced a near 1-to-1 block/scene mapping.
    # Audio energy stays flat throughout: musically this is ONE scene.
    blocks = [
        "Je ris de bon coeur",  # joie
        "Mon coeur bat pour toi",  # amour
        "Je pleure un peu",  # tristesse
        "La colere monte en moi",  # colere
        "Je me souviens d'hier",  # nostalgie
        "Je prie le ciel",  # spiritualite
        "On chante et on danse",  # celebration
        "Rien de plus a dire",  # default/contemplation
    ]
    lyrics = "\n\n".join(blocks)
    sections = [
        AudioSection(index=i, start=i * 5, end=(i + 1) * 5, energy="calme", local_tempo_bpm=100.0)
        for i in range(8)
    ]
    audio = AudioFeatures(duration=40.0, tempo_bpm=100.0, sections=sections)
    dna = build_project_dna(audio, genre="soul", director=DirectorSettings(), lyrics_text=lyrics)

    storyboard = build_storyboard_from_dna(dna, sections, lyrics_text=lyrics)

    assert len(storyboard.scenes) < len(blocks), (
        f"{len(storyboard.scenes)} scenes for {len(blocks)} differently-worded "
        "lyric blocks over flat-energy audio: scene count is still tracking "
        "lyric paragraph breaks instead of audio structure"
    )


def test_scene_boundaries_are_identical_with_and_without_lyrics_on_the_same_audio():
    sections = [
        AudioSection(index=i, start=i * 10, end=(i + 1) * 10, energy=e, local_tempo_bpm=100.0)
        for i, e in enumerate(["calme", "calme", "energique", "energique", "modere", "calme"])
    ]
    audio = AudioFeatures(duration=60.0, tempo_bpm=100.0, sections=sections)
    lyrics = (
        "Je ris de bon coeur\n\n"
        "Mon coeur bat pour toi\n\n"
        "Je pleure un peu\n\n"
        "La colere monte en moi\n\n"
        "Je me souviens d'hier\n\n"
        "On chante et on danse"
    )

    dna_no_lyrics = build_project_dna(audio, genre="soul", director=DirectorSettings())
    storyboard_no_lyrics = build_storyboard_from_dna(dna_no_lyrics, sections)

    dna_with_lyrics = build_project_dna(audio, genre="soul", director=DirectorSettings(), lyrics_text=lyrics)
    storyboard_with_lyrics = build_storyboard_from_dna(dna_with_lyrics, sections, lyrics_text=lyrics)

    boundaries_no_lyrics = [(s.start_seconds, s.end_seconds) for s in storyboard_no_lyrics.scenes]
    boundaries_with_lyrics = [(s.start_seconds, s.end_seconds) for s in storyboard_with_lyrics.scenes]
    assert boundaries_no_lyrics == boundaries_with_lyrics


def test_one_scene_can_still_span_several_distinct_lyric_blocks():
    # Direct, explicit check of "several verses can belong to the same
    # scene": flat energy across 4 sections, 4 differently-worded blocks ->
    # must collapse into one scene whose combined content draws on more
    # than one block. Kept under MAX_NARRATIVE_SCENE_SECONDS so the (separate,
    # pre-existing) max-scene-duration cap isn't what's being exercised here.
    blocks = ["Je ris de bon coeur", "Mon coeur bat pour toi", "Je pleure un peu", "La colere monte en moi"]
    lyrics = "\n\n".join(blocks)
    sections = [
        AudioSection(index=i, start=i * 5, end=(i + 1) * 5, energy="modere", local_tempo_bpm=100.0)
        for i in range(4)
    ]
    audio = AudioFeatures(duration=20.0, tempo_bpm=100.0, sections=sections)
    dna = build_project_dna(audio, genre="soul", director=DirectorSettings(), lyrics_text=lyrics)
    storyboard = build_storyboard_from_dna(dna, sections, lyrics_text=lyrics)

    assert len(storyboard.scenes) == 1
    assert storyboard.scenes[0].start_seconds == 0.0
    assert storyboard.scenes[0].end_seconds == 20.0
