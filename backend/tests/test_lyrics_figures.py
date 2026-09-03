"""detect_figures() is a weak, conservative linguistic signal -- these tests
lock in that it never turns a fleeting pronoun or an abstract/spiritual
referent into a false "someone else is here" signal."""
from app.lyrics_analysis import detect_figures


def test_pure_solo_narration_has_no_duo_or_collectif_hint():
    hints = detect_figures(["Je marche seul dans la nuit", "Je pense a mon chemin"])
    types = {h.pronoun_type for h in hints}
    assert types == {"solo"}


def test_recurring_second_person_is_flagged_as_duo_not_abstract():
    hints = detect_figures([
        "Tu es partie loin de moi",
        "Je pense a toi tous les jours",
        "Ton absence me pese",
    ])
    duo = next(h for h in hints if h.pronoun_type == "duo")
    assert duo.occurrences >= 2
    assert duo.likely_abstract is False


def test_recurring_collective_address_is_flagged_collectif():
    hints = detect_figures(["Nous dansons tous ensemble", "La foule vibre avec nous"])
    collectif = next(h for h in hints if h.pronoun_type == "collectif")
    assert collectif.occurrences == 2


def test_second_person_addressed_to_god_is_flagged_likely_abstract():
    hints = detect_figures(["Toi, mon Dieu, guide mes pas", "Je prie le ciel pour toi"])
    duo = next(h for h in hints if h.pronoun_type == "duo")
    assert duo.likely_abstract is True


def test_single_fleeting_mention_has_low_occurrence_count():
    hints = detect_figures(["Je marche seul", "Le vent souffle", "tu sais peut-etre un jour"])
    duo = next(h for h in hints if h.pronoun_type == "duo")
    assert duo.occurrences == 1


def test_empty_input_returns_no_hints():
    assert detect_figures([]) == []
    assert detect_figures(["", "   "]) == []
