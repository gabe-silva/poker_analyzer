"""Range shaping and continuation probability helpers."""

from __future__ import annotations

import math
import random
from typing import Sequence

from trainer.archetypes import Archetype
from trainer.cards import best_hand_rank, preflop_strength_score


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _made_hand_score(hole: Sequence[str], board: Sequence[str]) -> float:
    """Normalize current made-hand category to roughly [0, 1.3]."""
    if len(board) < 3:
        return 0.0
    rank = best_hand_rank(list(hole) + list(board))
    category = rank[0] / 8.0
    kicker = 0.0
    if rank[1]:
        kicker = rank[1][0] / 14.0
    return category + 0.3 * kicker


def sample_villain_hand(
    deck: Sequence[str],
    board: Sequence[str],
    street: str,
    archetype: Archetype,
    role: str,
    pressure: float,
    rng: random.Random,
) -> tuple[str, str]:
    """
    Sample a villain hand with rejection-sampling to mimic role/archetype ranges.

    pressure: 0.0 to 1.0, where higher means villain should continue tighter.
    """
    if len(deck) < 2:
        raise ValueError("Not enough cards in deck")

    role_tightness = {
        "bettor": 0.10,
        "caller": 0.02,
        "waiting": -0.05,
        "unknown": 0.0,
    }.get(role, 0.0)

    for _ in range(120):
        hand = tuple(rng.sample(list(deck), 2))
        pre = preflop_strength_score(hand[0], hand[1]) / 100.0

        post = 0.0
        if street != "preflop" and len(board) >= 3:
            post = _made_hand_score(hand, board)

        quality = 0.6 * pre + 0.4 * post
        target = archetype.preflop_tightness + role_tightness + pressure * 0.30
        target -= (archetype.bluff_factor - 0.4) * 0.15
        accept_prob = _sigmoid((quality - target) * 7.0)
        if rng.random() < accept_prob:
            return hand

    return tuple(rng.sample(list(deck), 2))


def continue_probability(
    archetype: Archetype,
    street: str,
    action_kind: str,
    size_pot_ratio: float,
    role: str,
) -> float:
    """Estimate villain continue frequency versus hero bet/raise."""
    if action_kind not in {"bet", "raise"}:
        raise ValueError("action_kind must be bet or raise")

    if action_kind == "raise":
        base = archetype.continue_vs_raise
    else:
        if street == "flop":
            base = 1.0 - archetype.fold_to_flop_bet
        elif street == "turn":
            base = 1.0 - archetype.fold_to_turn_bet
        elif street == "river":
            base = 1.0 - archetype.fold_to_river_bet
        else:
            base = 1.0 - archetype.fold_to_raise

    size_penalty = max(0.0, size_pot_ratio - 0.5) * 0.20
    role_adj = {"bettor": 0.08, "caller": 0.05, "waiting": -0.03, "unknown": 0.0}.get(role, 0.0)
    aggression_adj = (archetype.aggression - 0.5) * 0.14

    if street == "river":
        size_penalty *= 1.25

    return _clamp(base - size_penalty + role_adj + aggression_adj, 0.05, 0.95)

