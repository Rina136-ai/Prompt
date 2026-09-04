"""Turns raw lyrics into a labeled section structure with a rough mood per section.

This is a heuristic analysis (no external NLP service): it splits on blank
lines, finds the chorus by looking for a block that repeats, and scores each
section against a small keyword lexicon to guess its dominant mood/theme.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

MOOD_LEXICON: dict[str, list[str]] = {
    "joie": ["danse", "sourire", "rire", "fete", "soleil", "bonheur", "celebrer", "liberte"],
    "amour": ["amour", "coeur", "aimer", "baiser", "tendresse", "toujours", "ensemble"],
    "tristesse": ["pleure", "larme", "seul", "manque", "adieu", "regret", "douleur", "perdu"],
    "colere": ["colere", "trahi", "menteur", "combat", "rage", "injustice"],
    "nostalgie": ["souvenir", "hier", "enfance", "autrefois", "rappelle", "passe"],
    "spiritualite": ["dieu", "priere", "ame", "ciel", "esprit", "foi", "benir"],
    "celebration": ["fete", "danser", "chanter", "musique", "rythme", "vibrer"],
}

_DEFAULT_MOOD = "contemplation"

# Weak signal for who/what the lyrics address -- NOT a casting rule by itself.
# "solo" markers never add a character (the narrator is already represented).
# See project_dna.py for the conservative promotion logic that decides
# whether a "duo"/"collectif" hint becomes an actual visible character.
FIGURE_LEXICON: dict[str, list[str]] = {
    "solo": ["je", "j'ai", "moi", "me", "m'appelle"],
    "duo": ["tu", "toi", "t'aime", "ton coeur", "ta main", "mon amour"],
    "collectif": ["nous", "on danse", "tous", "ensemble", "la foule", "vous"],
}

# Within "collectif", "nous"/"tous"/"vous" are common function words used in
# countless non-referential turns of phrase ("on nous dit que...", "pour
# tous les...") and must never justify a visible group by themselves, no
# matter how often they recur. Only these keywords unambiguously describe an
# actual group presence/action; a group character requires at least one of
# them (see FigureHint.has_strong_evidence / project_dna._build_cast).
_STRONG_FIGURE_KEYWORDS: dict[str, set[str]] = {
    "collectif": {"on danse", "la foule", "ensemble"},
}

# Referents that usually name something abstract, spiritual, or absent rather
# than a person who should appear on screen. A "duo"/"collectif" hint found
# alongside these words is flagged likely_abstract=True.
ABSTRACT_REFERENT_LEXICON = [
    "dieu", "seigneur", "le ciel", "la vie", "le temps", "mon pays",
    "la liberte", "l'esprit", "l'ame", "le destin", "la mort",
]


@dataclass
class FigureHint:
    pronoun_type: str  # "solo" | "duo" | "collectif"
    matched_keywords: list[str]
    occurrences: int  # number of distinct text segments where this type was found (recurrence, not raw word count)
    likely_abstract: bool
    has_strong_evidence: bool = True  # False only when a type with weak/strong keywords (see _STRONG_FIGURE_KEYWORDS) matched exclusively on weak ones


def detect_figures(text_segments: list[str]) -> list[FigureHint]:
    """Scans lyrics/transcription text for who the song addresses.

    This is deliberately weak and conservative: it flags patterns, it does
    not decide who gets rendered as a character. A "tu" could be a lover, a
    dead parent, or God -- this function only reports the raw signal
    (pronoun_type + whether abstract/spiritual words co-occur); the casting
    decision itself lives in project_dna.py, and defaults to caution.
    """
    matching_segment_count: dict[str, int] = {ptype: 0 for ptype in FIGURE_LEXICON}
    abstract_segment_count: dict[str, int] = {ptype: 0 for ptype in FIGURE_LEXICON}
    strong_segment_count: dict[str, int] = {ptype: 0 for ptype in FIGURE_LEXICON}
    matched_kw: dict[str, set] = {ptype: set() for ptype in FIGURE_LEXICON}

    for segment in text_segments:
        normalized = _normalize(segment)
        if not normalized:
            continue
        words = set(normalized.split())
        segment_is_abstract = any(_normalize(ref) in normalized for ref in ABSTRACT_REFERENT_LEXICON)

        for ptype, keywords in FIGURE_LEXICON.items():
            hits = [kw for kw in keywords if _normalize(kw) in words or _normalize(kw) in normalized]
            if not hits:
                continue
            matching_segment_count[ptype] += 1
            matched_kw[ptype].update(hits)
            if segment_is_abstract:
                abstract_segment_count[ptype] += 1
            strong_keywords = _STRONG_FIGURE_KEYWORDS.get(ptype)
            if strong_keywords and any(_normalize(kw) in normalized for kw in strong_keywords):
                strong_segment_count[ptype] += 1

    hints: list[FigureHint] = []
    for ptype in FIGURE_LEXICON:
        count = matching_segment_count[ptype]
        if count == 0:
            continue
        likely_abstract = abstract_segment_count[ptype] >= (count / 2)
        # Types without a strong/weak split (solo, duo) are unaffected: only
        # a type listed in _STRONG_FIGURE_KEYWORDS can end up "not strong".
        has_strong_evidence = ptype not in _STRONG_FIGURE_KEYWORDS or strong_segment_count[ptype] > 0
        hints.append(
            FigureHint(
                pronoun_type=ptype,
                matched_keywords=sorted(matched_kw[ptype]),
                occurrences=count,
                likely_abstract=likely_abstract,
                has_strong_evidence=has_strong_evidence,
            )
        )
    return hints


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


@dataclass
class LyricsSection:
    index: int
    label: str
    text: str
    is_chorus: bool = False
    mood: str = _DEFAULT_MOOD
    keywords: list[str] = field(default_factory=list)


def split_into_blocks(lyrics: str) -> list[str]:
    blocks = [b.strip() for b in re.split(r"\n\s*\n", lyrics.strip()) if b.strip()]
    return blocks


def score_mood(text: str) -> tuple[str, list[str]]:
    normalized = _normalize(text)
    words = set(normalized.split())
    best_mood = _DEFAULT_MOOD
    best_score = 0
    matched: list[str] = []
    for mood, keywords in MOOD_LEXICON.items():
        hits = [kw for kw in keywords if kw in words or kw in normalized]
        if len(hits) > best_score:
            best_score = len(hits)
            best_mood = mood
            matched = hits
    return best_mood, matched


def analyze_lyrics(lyrics: str, chorus_similarity_threshold: float = 0.72) -> list[LyricsSection]:
    """Split lyrics into labeled sections (Introduction/Couplet/Refrain/Pont/Outro)."""
    blocks = split_into_blocks(lyrics)
    if not blocks:
        return []

    # A block is a chorus candidate if it's near-duplicate of another block.
    chorus_group: list[int] = []
    for i, block_a in enumerate(blocks):
        for j, block_b in enumerate(blocks):
            if i != j and _similarity(block_a, block_b) >= chorus_similarity_threshold:
                chorus_group.append(i)
                break

    sections: list[LyricsSection] = []
    verse_count = 0
    for i, block in enumerate(blocks):
        is_chorus = i in chorus_group
        if is_chorus:
            label = "Refrain"
        elif i == 0 and len(block.splitlines()) <= 2:
            label = "Introduction"
        elif i == len(blocks) - 1 and len(block.splitlines()) <= 2:
            label = "Outro"
        elif not is_chorus and i > 0 and len(chorus_group) >= 2 and i > min(chorus_group) and i not in chorus_group and _is_bridge_position(i, chorus_group, len(blocks)):
            label = "Pont"
        else:
            verse_count += 1
            label = f"Couplet {verse_count}"

        mood, keywords = score_mood(block)
        sections.append(
            LyricsSection(index=i, label=label, text=block, is_chorus=is_chorus, mood=mood, keywords=keywords)
        )
    return sections


def _is_bridge_position(i: int, chorus_group: list[int], total_blocks: int) -> bool:
    """A lone, non-chorus block appearing after most choruses, near the end, reads as a bridge."""
    if not chorus_group:
        return False
    last_chorus = max(chorus_group)
    return i > last_chorus and i < total_blocks - 1


def overall_mood(sections: list[LyricsSection]) -> str:
    if not sections:
        return _DEFAULT_MOOD
    counts: dict[str, int] = {}
    for s in sections:
        counts[s.mood] = counts.get(s.mood, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0]
