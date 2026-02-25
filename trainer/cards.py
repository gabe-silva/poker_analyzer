"""Card utilities, lightweight hand evaluator, and range features."""

from __future__ import annotations

from itertools import combinations
from typing import Iterable, List, Sequence, Tuple

from trainer.constants import CARD_RANKS, CARD_SUITS

RANK_TO_VALUE = {r: i + 2 for i, r in enumerate(CARD_RANKS)}
VALUE_TO_RANK = {v: r for r, v in RANK_TO_VALUE.items()}


def full_deck() -> List[str]:
    """Return an ordered 52-card deck in rank/suit notation."""
    return [f"{r}{s}" for r in CARD_RANKS for s in CARD_SUITS]


def card_rank(card: str) -> int:
    return RANK_TO_VALUE[card[0]]


def card_suit(card: str) -> str:
    return card[1]


def remove_cards(deck: List[str], cards: Iterable[str]) -> List[str]:
    used = set(cards)
    return [c for c in deck if c not in used]


def _straight_high(ranks: Sequence[int]) -> int:
    """Return high card of straight if present, else 0."""
    unique = sorted(set(ranks))
    if len(unique) < 5:
        return 0
    if {14, 5, 4, 3, 2}.issubset(unique):
        return 5
    for i in range(len(unique) - 4):
        window = unique[i : i + 5]
        if window[-1] - window[0] == 4 and len(window) == 5:
            return window[-1]
    return 0


def hand_rank_5(cards: Sequence[str]) -> Tuple[int, Tuple[int, ...]]:
    """
    Rank a 5-card poker hand.

    Returns:
        (category, tiebreakers) where larger tuple compares better.
        Categories:
            8: straight flush
            7: four of a kind
            6: full house
            5: flush
            4: straight
            3: three of a kind
            2: two pair
            1: one pair
            0: high card
    """
    if len(cards) != 5:
        raise ValueError("hand_rank_5 requires exactly 5 cards")

    ranks = [card_rank(c) for c in cards]
    suits = [card_suit(c) for c in cards]

    rank_counts: dict[int, int] = {}
    for r in ranks:
        rank_counts[r] = rank_counts.get(r, 0) + 1

    ordered_counts = sorted(
        rank_counts.items(),
        key=lambda kv: (kv[1], kv[0]),
        reverse=True,
    )

    is_flush = len(set(suits)) == 1
    straight_high = _straight_high(ranks)
    is_straight = straight_high > 0

    if is_flush and is_straight:
        return (8, (straight_high,))

    top_rank, top_count = ordered_counts[0]
    if top_count == 4:
        kicker = max(r for r in ranks if r != top_rank)
        return (7, (top_rank, kicker))

    if top_count == 3 and len(ordered_counts) > 1 and ordered_counts[1][1] == 2:
        return (6, (top_rank, ordered_counts[1][0]))

    if is_flush:
        return (5, tuple(sorted(ranks, reverse=True)))

    if is_straight:
        return (4, (straight_high,))

    if top_count == 3:
        kickers = sorted((r for r in ranks if r != top_rank), reverse=True)
        return (3, (top_rank, *kickers))

    pairs = [r for r, count in ordered_counts if count == 2]
    if len(pairs) == 2:
        high_pair, low_pair = sorted(pairs, reverse=True)
        kicker = max(r for r in ranks if r not in (high_pair, low_pair))
        return (2, (high_pair, low_pair, kicker))

    if len(pairs) == 1:
        pair = pairs[0]
        kickers = sorted((r for r in ranks if r != pair), reverse=True)
        return (1, (pair, *kickers))

    return (0, tuple(sorted(ranks, reverse=True)))


def best_hand_rank(cards: Sequence[str]) -> Tuple[int, Tuple[int, ...]]:
    """Rank best 5-card hand from 5-7 cards."""
    if len(cards) < 5 or len(cards) > 7:
        raise ValueError("best_hand_rank requires 5 to 7 cards")
    if len(cards) == 5:
        return hand_rank_5(cards)
    best = (-1, tuple())
    for combo in combinations(cards, 5):
        rank = hand_rank_5(combo)
        if rank > best:
            best = rank
    return best


def compare_hands(cards_a: Sequence[str], cards_b: Sequence[str]) -> int:
    """Compare two 5-7-card hands. 1 if A wins, -1 if B wins, 0 tie."""
    ra = best_hand_rank(cards_a)
    rb = best_hand_rank(cards_b)
    if ra > rb:
        return 1
    if rb > ra:
        return -1
    return 0


def rank_category_name(rank: Tuple[int, Tuple[int, ...]]) -> str:
    names = {
        8: "Straight Flush",
        7: "Four of a Kind",
        6: "Full House",
        5: "Flush",
        4: "Straight",
        3: "Three of a Kind",
        2: "Two Pair",
        1: "Pair",
        0: "High Card",
    }
    return names[rank[0]]


def preflop_strength_score(card_a: str, card_b: str) -> float:
    """Heuristic 0-100 strength score for two-card hand quality."""
    r1 = card_rank(card_a)
    r2 = card_rank(card_b)
    suited = card_suit(card_a) == card_suit(card_b)
    high = max(r1, r2)
    low = min(r1, r2)

    score = high * 3.0 + low * 2.0
    if r1 == r2:
        score += 24.0 + r1 * 1.5
    if suited:
        score += 4.0
    gap = abs(r1 - r2)
    if gap == 1:
        score += 4.0
    elif gap == 2:
        score += 2.0
    elif gap >= 4:
        score -= 2.0
    if high >= 11:
        score += 2.0
    return max(0.0, min(100.0, score))


def board_texture_score(board: Sequence[str]) -> float:
    """Rough texture score; higher means wetter board."""
    if len(board) < 3:
        return 0.0
    ranks = sorted((card_rank(c) for c in board), reverse=True)
    suits = [card_suit(c) for c in board]
    suit_counts: dict[str, int] = {}
    for s in suits:
        suit_counts[s] = suit_counts.get(s, 0) + 1
    max_suit = max(suit_counts.values())
    connected = 0
    for a, b in zip(ranks, ranks[1:]):
        if abs(a - b) <= 2:
            connected += 1
    paired = len(set(ranks)) < len(ranks)
    texture = 0.0
    texture += 0.9 * max(0, max_suit - 2)
    texture += 0.6 * connected
    texture += 0.8 if paired else 0.0
    return texture

