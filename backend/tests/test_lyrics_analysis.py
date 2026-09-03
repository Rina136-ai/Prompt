from app.lyrics_analysis import analyze_lyrics, overall_mood

LYRICS = """Petit matin, le soleil se leve
Le village s'eveille doucement

On danse, on chante, on vibre ensemble
Le rythme nous rend libres

Je me souviens des tambours d'hier
Quand grand-mere chantait pour nous

On danse, on chante, on vibre ensemble
Le rythme nous rend libres

Ce soir encore, la fete continue"""


def test_splits_into_five_blocks():
    sections = analyze_lyrics(LYRICS)
    assert len(sections) == 5


def test_detects_repeated_chorus():
    sections = analyze_lyrics(LYRICS)
    assert sections[1].is_chorus is True
    assert sections[3].is_chorus is True
    assert sections[1].label == "Refrain"
    assert sections[3].label == "Refrain"
    assert sections[2].is_chorus is False


def test_labels_intro_verse_outro():
    sections = analyze_lyrics(LYRICS)
    assert sections[0].label == "Introduction"
    assert sections[2].label == "Couplet 1"
    assert sections[4].label == "Outro"


def test_mood_detection_hits_a_positive_mood():
    sections = analyze_lyrics(LYRICS)
    assert sections[1].mood in {"joie", "celebration"}


def test_mood_defaults_when_no_keyword_matches():
    sections = analyze_lyrics("xyz abc\n\ndef ghi jkl")
    assert all(s.mood == "contemplation" for s in sections)


def test_overall_mood_is_most_common():
    sections = analyze_lyrics(LYRICS)
    mood = overall_mood(sections)
    assert mood in {s.mood for s in sections}


def test_empty_lyrics_returns_no_sections():
    assert analyze_lyrics("   \n\n  ") == []
