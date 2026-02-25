"""Opponent archetype definitions used by scenario generation and EV logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class Archetype:
    """Compact profile used for exploit-style decision modeling."""

    key: str
    label: str
    description: str
    vpip: float
    pfr: float
    af: float
    preflop_tightness: float
    fold_to_flop_bet: float
    fold_to_turn_bet: float
    fold_to_river_bet: float
    fold_to_raise: float
    continue_vs_raise: float
    check_raise_rate: float
    aggression: float
    bluff_factor: float


ARCHETYPES: Dict[str, Archetype] = {
    "nit": Archetype(
        key="nit",
        label="Nit",
        description="Very selective range, avoids high-variance spots.",
        vpip=0.14,
        pfr=0.11,
        af=1.7,
        preflop_tightness=0.82,
        fold_to_flop_bet=0.58,
        fold_to_turn_bet=0.62,
        fold_to_river_bet=0.68,
        fold_to_raise=0.63,
        continue_vs_raise=0.28,
        check_raise_rate=0.06,
        aggression=0.32,
        bluff_factor=0.24,
    ),
    "tag_reg": Archetype(
        key="tag_reg",
        label="TAG Reg",
        description="Solid balanced player with disciplined ranges.",
        vpip=0.22,
        pfr=0.19,
        af=2.6,
        preflop_tightness=0.67,
        fold_to_flop_bet=0.44,
        fold_to_turn_bet=0.48,
        fold_to_river_bet=0.53,
        fold_to_raise=0.47,
        continue_vs_raise=0.43,
        check_raise_rate=0.11,
        aggression=0.56,
        bluff_factor=0.41,
    ),
    "lag_reg": Archetype(
        key="lag_reg",
        label="LAG Reg",
        description="Wide ranges, frequent pressure and barreling.",
        vpip=0.34,
        pfr=0.27,
        af=3.4,
        preflop_tightness=0.46,
        fold_to_flop_bet=0.34,
        fold_to_turn_bet=0.39,
        fold_to_river_bet=0.47,
        fold_to_raise=0.39,
        continue_vs_raise=0.55,
        check_raise_rate=0.17,
        aggression=0.78,
        bluff_factor=0.67,
    ),
    "calling_station": Archetype(
        key="calling_station",
        label="Loose-Passive Calling Station",
        description="Calls too much, under-bluffs, hates folding pairs.",
        vpip=0.46,
        pfr=0.11,
        af=1.1,
        preflop_tightness=0.34,
        fold_to_flop_bet=0.23,
        fold_to_turn_bet=0.31,
        fold_to_river_bet=0.42,
        fold_to_raise=0.26,
        continue_vs_raise=0.71,
        check_raise_rate=0.04,
        aggression=0.21,
        bluff_factor=0.19,
    ),
    "maniac": Archetype(
        key="maniac",
        label="Maniac",
        description="Extreme aggression and over-bluff frequency.",
        vpip=0.52,
        pfr=0.37,
        af=4.4,
        preflop_tightness=0.27,
        fold_to_flop_bet=0.28,
        fold_to_turn_bet=0.35,
        fold_to_river_bet=0.43,
        fold_to_raise=0.34,
        continue_vs_raise=0.62,
        check_raise_rate=0.23,
        aggression=0.91,
        bluff_factor=0.83,
    ),
    "weak_tight": Archetype(
        key="weak_tight",
        label="Weak-Tight",
        description="Risk-averse and overfolds to sustained pressure.",
        vpip=0.19,
        pfr=0.13,
        af=1.6,
        preflop_tightness=0.73,
        fold_to_flop_bet=0.53,
        fold_to_turn_bet=0.61,
        fold_to_river_bet=0.66,
        fold_to_raise=0.58,
        continue_vs_raise=0.31,
        check_raise_rate=0.05,
        aggression=0.28,
        bluff_factor=0.22,
    ),
    "fit_or_fold": Archetype(
        key="fit_or_fold",
        label="Fit-or-Fold Flop Player",
        description="Continues when connected; otherwise gives up quickly.",
        vpip=0.26,
        pfr=0.19,
        af=2.0,
        preflop_tightness=0.57,
        fold_to_flop_bet=0.59,
        fold_to_turn_bet=0.48,
        fold_to_river_bet=0.50,
        fold_to_raise=0.52,
        continue_vs_raise=0.36,
        check_raise_rate=0.08,
        aggression=0.44,
        bluff_factor=0.31,
    ),
    "one_and_done": Archetype(
        key="one_and_done",
        label="One-and-Done C-Bettor",
        description="C-bets frequently but under-barrels on turns.",
        vpip=0.24,
        pfr=0.2,
        af=2.2,
        preflop_tightness=0.61,
        fold_to_flop_bet=0.42,
        fold_to_turn_bet=0.58,
        fold_to_river_bet=0.59,
        fold_to_raise=0.49,
        continue_vs_raise=0.4,
        check_raise_rate=0.1,
        aggression=0.53,
        bluff_factor=0.36,
    ),
    "trappy": Archetype(
        key="trappy",
        label="Trappy Slow-Player",
        description="Slow-plays nutted hands and under-raises value.",
        vpip=0.23,
        pfr=0.16,
        af=1.7,
        preflop_tightness=0.64,
        fold_to_flop_bet=0.38,
        fold_to_turn_bet=0.43,
        fold_to_river_bet=0.5,
        fold_to_raise=0.44,
        continue_vs_raise=0.47,
        check_raise_rate=0.13,
        aggression=0.36,
        bluff_factor=0.27,
    ),
    "overfolder_3bet": Archetype(
        key="overfolder_3bet",
        label="Overfolder vs 3-Bets",
        description="Opens reasonable range but folds too often to reraises.",
        vpip=0.25,
        pfr=0.2,
        af=2.1,
        preflop_tightness=0.6,
        fold_to_flop_bet=0.43,
        fold_to_turn_bet=0.47,
        fold_to_river_bet=0.52,
        fold_to_raise=0.61,
        continue_vs_raise=0.33,
        check_raise_rate=0.09,
        aggression=0.49,
        bluff_factor=0.34,
    ),
    "overcaller_preflop": Archetype(
        key="overcaller_preflop",
        label="Overcaller Preflop",
        description="Calls preflop too wide and arrives postflop with dominated holdings.",
        vpip=0.37,
        pfr=0.16,
        af=2.0,
        preflop_tightness=0.45,
        fold_to_flop_bet=0.36,
        fold_to_turn_bet=0.45,
        fold_to_river_bet=0.54,
        fold_to_raise=0.41,
        continue_vs_raise=0.51,
        check_raise_rate=0.1,
        aggression=0.41,
        bluff_factor=0.29,
    ),
    "short_stack_jammer": Archetype(
        key="short_stack_jammer",
        label="Short-Stack Jammer",
        description="Lower SPR strategy with shove-heavy branches.",
        vpip=0.29,
        pfr=0.22,
        af=3.0,
        preflop_tightness=0.55,
        fold_to_flop_bet=0.32,
        fold_to_turn_bet=0.37,
        fold_to_river_bet=0.46,
        fold_to_raise=0.3,
        continue_vs_raise=0.64,
        check_raise_rate=0.16,
        aggression=0.74,
        bluff_factor=0.44,
    ),
}


def archetype_by_key(key: str) -> Archetype:
    """Lookup helper with strict validation."""
    if key not in ARCHETYPES:
        raise KeyError(f"Unknown archetype: {key}")
    return ARCHETYPES[key]


def archetype_options() -> list[dict]:
    """Serialize archetypes for UI dropdowns."""
    return [
        {
            "key": v.key,
            "label": v.label,
            "description": v.description,
            "vpip": v.vpip,
            "pfr": v.pfr,
            "af": v.af,
        }
        for v in ARCHETYPES.values()
    ]

