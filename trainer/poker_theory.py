"""Core poker-theory math helpers used by EV coaching explanations.

This module intentionally keeps formulas explicit and testable so coaching text
can cite exact thresholds (pot odds, MDF, bluff break-even fold rate, SPR).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def required_equity_to_call(pot_before_call: float, call_amount: float) -> float:
    """
    Break-even equity for a call.

    Formula: call / (pot + call)
    """
    pot = max(0.0, float(pot_before_call))
    call = max(0.0, float(call_amount))
    if call <= 0:
        return 0.0
    return call / max(1e-9, pot + call)


def minimum_defense_frequency(pot_before_bet: float, bet_size: float) -> float:
    """
    Minimum defense frequency against a pure bluffing strategy.

    Formula: pot / (pot + bet)
    """
    pot = max(0.0, float(pot_before_bet))
    bet = max(0.0, float(bet_size))
    if bet <= 0:
        return 1.0
    return _clamp(pot / max(1e-9, pot + bet), 0.0, 1.0)


def break_even_bluff_fold_frequency(risk: float, reward: float) -> float:
    """
    Required fold percentage for a zero-equity bluff.

    Formula: risk / (risk + reward)
    """
    r = max(0.0, float(risk))
    w = max(0.0, float(reward))
    if r <= 0:
        return 0.0
    return _clamp(r / max(1e-9, r + w), 0.0, 1.0)


def polarized_bluff_share(bet_to_pot_ratio: float) -> float:
    """
    Bluff share of betting range on a pure river polarization model.

    Formula: b / (1 + b), where b = bet/pot.
    """
    b = max(0.0, float(bet_to_pot_ratio))
    if b <= 0:
        return 0.0
    return _clamp(b / (1.0 + b), 0.0, 1.0)


def bluff_to_value_ratio(bet_to_pot_ratio: float) -> float:
    """
    Bluff:value ratio under a polarized one-street model.

    Ratio = bet/pot.
    """
    return max(0.0, float(bet_to_pot_ratio))


def stack_to_pot_ratio(effective_stack: float, pot_size: float) -> float:
    """Compute SPR (effective stack divided by pot size)."""
    stack = max(0.0, float(effective_stack))
    pot = max(1e-9, float(pot_size))
    return stack / pot


@dataclass(frozen=True)
class SprBand:
    label: str
    notes: List[str]


def classify_spr(spr: float) -> SprBand:
    """Rule-of-thumb SPR bands for action planning."""
    s = max(0.0, float(spr))
    if s < 2.0:
        return SprBand(
            label="Very Low SPR",
            notes=[
                "Commitment threshold is low; value edges realize quickly.",
                "Avoid high-frequency pure bluffs unless fold equity is clear.",
            ],
        )
    if s < 4.5:
        return SprBand(
            label="Low SPR",
            notes=[
                "One-pair plus strong draws gain stack-off value more often.",
                "Pressure lines should be size-disciplined to avoid over-investing weak bluff-catchers.",
            ],
        )
    if s < 8.0:
        return SprBand(
            label="Medium SPR",
            notes=[
                "Mix value and pressure; future-street realization matters.",
                "Favor hands with redraws/blockers when building aggressive lines.",
            ],
        )
    return SprBand(
        label="High SPR",
        notes=[
            "Nutted potential rises in value; medium made hands become thinner stacks-off.",
            "Use selective aggression and protect against reverse implied odds.",
        ],
    )


def common_mdf_reference() -> List[Dict[str, float]]:
    """Quick MDF table for common bet sizes."""
    bet_sizes = [0.25, 0.33, 0.5, 0.66, 0.75, 1.0, 1.5]
    out: List[Dict[str, float]] = []
    for b in bet_sizes:
        mdf = minimum_defense_frequency(1.0, b)
        out.append({"bet_to_pot": b, "mdf": round(mdf, 4)})
    return out
