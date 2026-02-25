"""Shared constants for the cash-game trainer."""

from __future__ import annotations

from typing import Dict, List

STREETS = ["preflop", "flop", "turn", "river"]
NODE_TYPES = ["single_raised_pot", "three_bet_pot", "four_bet_pot"]
ACTION_CONTEXTS = ["checked_to_hero", "facing_bet", "facing_bet_and_call"]

POSITION_SETS: Dict[int, List[str]] = {
    2: ["BTN", "BB"],
    3: ["BTN", "SB", "BB"],
    4: ["BTN", "SB", "BB", "UTG"],
    5: ["BTN", "SB", "BB", "UTG", "CO"],
    6: ["BTN", "SB", "BB", "UTG", "HJ", "CO"],
    7: ["BTN", "SB", "BB", "UTG", "LJ", "HJ", "CO"],
}

CARD_RANKS = "23456789TJQKA"
CARD_SUITS = "cdhs"

BET_SIZE_PCTS = [0.33, 0.5, 0.75, 1.25]
DEFAULT_SB = 1.0
DEFAULT_BB = 2.0
DEFAULT_STACK_BB = 100.0


def positions_for_table(num_players: int) -> List[str]:
    """Return ordered positions for table size."""
    if num_players not in POSITION_SETS:
        raise ValueError("num_players must be between 2 and 7")
    return POSITION_SETS[num_players]

