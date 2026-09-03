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
