"""Hero profile modeling for VPIP/PFR/AF-aware strategy and EV adjustments."""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Dict, List, Tuple


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _normalize_rate(raw: float, default: float) -> float:
    """Accept either decimal or percent-like input."""
    if raw is None:
        return default
    value = float(raw)
    if value > 1.0:
        value /= 100.0
    return _clamp(value, 0.0, 1.0)


POS_OPEN_TARGETS: Dict[str, Tuple[float, float]] = {
    "UTG": (0.17, 0.23),
    "LJ": (0.20, 0.27),
    "HJ": (0.22, 0.30),
    "CO": (0.30, 0.39),
    "BTN": (0.44, 0.60),
    "SB": (0.35, 0.48),
    "BB": (0.00, 0.00),
}


@dataclass(frozen=True)
class HeroProfile:
    """Hero style metrics used in exploit feedback and EV adjustments."""

    vpip: float
    pfr: float
    af: float
    three_bet: float
    fold_to_3bet: float

    @property
    def vpip_pfr_gap(self) -> float:
        return max(0.0, self.vpip - self.pfr)

    @property
    def preflop_aggression_ratio(self) -> float:
        if self.vpip <= 0:
            return 0.0
        return self.pfr / self.vpip

    @property
    def image_bluffiness(self) -> float:
        """How bluffy/villains perceive hero likely to be (0-1)."""
        af_norm = _clamp(self.af / 5.0, 0.0, 1.0)
        ratio_norm = _clamp(self.preflop_aggression_ratio, 0.0, 1.0)
        return _clamp(
            0.42 * self.vpip + 0.34 * self.pfr + 0.14 * af_norm + 0.10 * ratio_norm,
            0.0,
            1.0,
        )

    @property
    def style_label(self) -> str:
        if self.vpip < 0.17 and self.pfr < 0.13:
            return "Nit / Tight-Passive"
        if self.vpip < 0.24 and self.pfr >= 0.16 and self.af >= 2.0:
            return "TAG"
        if self.vpip >= 0.28 and self.pfr >= 0.20 and self.af >= 2.2:
            return "LAG"
        if self.vpip >= 0.30 and self.pfr < 0.17:
            return "Loose-Passive"
        if self.af >= 4.0 and self.vpip >= 0.35:
            return "Maniac / Over-aggressive"
        return "Hybrid / Transitional"

    def leak_flags(self) -> List[str]:
        flags: List[str] = []
        if self.vpip_pfr_gap > 0.10:
            flags.append("Large VPIP-PFR gap: likely overcalling preflop.")
        if self.preflop_aggression_ratio < 0.62 and self.vpip > 0.25:
            flags.append("Low raise-to-play ratio: not converting enough opens to raises.")
        if self.af > 4.0:
            flags.append("Very high AF: likely over-bluffing late streets.")
        if self.fold_to_3bet > 0.65:
            flags.append("High fold to 3-bet: opponents can re-raise light.")
        if self.three_bet < 0.05:
            flags.append("Low 3-bet rate: value-heavy and potentially face-up.")
        return flags

    def position_guidance(self, position: str, street: str) -> dict:
        low, high = POS_OPEN_TARGETS.get(position, (0.22, 0.30))
        notes: List[str] = []

        if position == "BTN":
            notes.append("Apply widest pressure here; isolate stations with larger sizings.")
        if position in {"SB", "BB"}:
            notes.append("OOP penalty is real: reduce low-equity bluffs and avoid bloating marginal pots.")
        if position in {"UTG", "LJ", "HJ"}:
            notes.append("Use tighter value-heavy opens; preserve EV by avoiding dominated offsuit broadways.")
        if street in {"turn", "river"} and self.af > 3.6:
            notes.append("Your AF is high: tighten river bluffs and keep value density high.")
        if self.vpip_pfr_gap > 0.10:
            notes.append("You call too much versus your opens: convert best call candidates into raises.")

        return {
            "position": position,
            "street": street,
            "target_open_vpip_range": [round(low, 3), round(high, 3)],
            "style_label": self.style_label,
            "notes": notes,
        }

    def to_dict(self) -> dict:
        return {
            "vpip": round(self.vpip, 4),
            "pfr": round(self.pfr, 4),
            "af": round(self.af, 3),
            "three_bet": round(self.three_bet, 4),
            "fold_to_3bet": round(self.fold_to_3bet, 4),
            "vpip_pfr_gap": round(self.vpip_pfr_gap, 4),
            "preflop_aggression_ratio": round(self.preflop_aggression_ratio, 4),
            "image_bluffiness": round(self.image_bluffiness, 4),
            "style_label": self.style_label,
            "leak_flags": self.leak_flags(),
        }


def parse_hero_profile(raw: dict | None) -> HeroProfile:
    """Normalize user-supplied profile with robust defaults."""
    raw = raw or {}
    return HeroProfile(
        vpip=_normalize_rate(raw.get("vpip"), 0.30),
        pfr=_normalize_rate(raw.get("pfr"), 0.22),
        af=_clamp(float(raw.get("af", 2.8)), 0.4, 8.0),
        three_bet=_normalize_rate(raw.get("three_bet"), 0.09),
        fold_to_3bet=_normalize_rate(raw.get("fold_to_3bet"), 0.54),
    )


def randomize_hero_profile(rng: random.Random) -> HeroProfile:
    """
    Generate a wide-range randomized hero profile.

    Ranges are intentionally broad so drills include tight, balanced, and high-pressure images.
    """
    vpip = rng.uniform(0.13, 0.56)
    max_pfr = max(0.08, vpip - rng.uniform(0.01, 0.14))
    pfr = rng.uniform(0.08, min(0.44, max_pfr))
    af = rng.uniform(0.9, 6.3)
    three_bet = rng.uniform(0.025, 0.19)
    fold_to_3bet = rng.uniform(0.20, 0.82)

    # Keep realistic relationship between VPIP/PFR and 3-bet:
    if vpip < 0.20:
        three_bet = min(three_bet, rng.uniform(0.02, 0.10))
    if pfr > 0.30:
        three_bet = max(three_bet, rng.uniform(0.08, 0.17))

    return HeroProfile(
        vpip=_clamp(vpip, 0.08, 0.65),
        pfr=_clamp(pfr, 0.05, 0.50),
        af=_clamp(af, 0.4, 8.0),
        three_bet=_clamp(three_bet, 0.01, 0.30),
        fold_to_3bet=_clamp(fold_to_3bet, 0.10, 0.90),
    )
