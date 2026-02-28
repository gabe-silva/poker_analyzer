"""EV approximation engine with leak-factor explanations."""

from __future__ import annotations

import math
import random
from copy import deepcopy
from dataclasses import dataclass
from collections import Counter
from typing import Dict, List, Optional, Sequence, Tuple

from trainer.archetypes import archetype_by_key
from trainer.cards import (
    best_hand_rank,
    board_texture_score,
    card_rank,
    card_suit,
    full_deck,
    remove_cards,
)
from trainer.hero_profile import HeroProfile, parse_hero_profile
from trainer.poker_theory import (
    bluff_to_value_ratio,
    break_even_bluff_fold_frequency,
    classify_spr,
    minimum_defense_frequency,
    polarized_bluff_share,
    required_equity_to_call,
    stack_to_pot_ratio,
)
from trainer.range_model import continue_probability, sample_villain_hand


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _position_bonus(position: str) -> float:
    table = {
        "BTN": 0.08,
        "CO": 0.05,
        "HJ": 0.03,
        "LJ": 0.01,
        "UTG": -0.01,
        "SB": -0.08,
        "BB": -0.05,
    }
    return table.get(position, 0.0)


def _future_factor(street: str) -> float:
    return {"preflop": 2.2, "flop": 1.45, "turn": 1.2, "river": 1.0}[street]


def _normalize_choice(decision: dict) -> tuple:
    action = str(decision.get("action", "")).lower()
    size = decision.get("size_bb")
    intent = decision.get("intent")
    size_norm = None if size in (None, "", 0) else round(float(size), 1)
    intent_norm = None if not intent else str(intent).lower()
    return action, size_norm, intent_norm


def _street_fold_rate(archetype_key: str, street: str) -> float:
    archetype = archetype_by_key(archetype_key)
    if street == "flop":
        return float(archetype.fold_to_flop_bet)
    if street == "turn":
        return float(archetype.fold_to_turn_bet)
    if street == "river":
        return float(archetype.fold_to_river_bet)
    return float(archetype.fold_to_raise)


def _texture_label(texture: float) -> str:
    if texture < 0.7:
        return "dry"
    if texture < 1.6:
        return "semi-wet"
    return "wet"


def _summarize_archetype_mix(villains: Sequence[dict]) -> str:
    if not villains:
        return "no active villains"
    counts = Counter(v["archetype_key"] for v in villains)
    most_common = counts.most_common(2)
    chunks = []
    for key, n in most_common:
        label = archetype_by_key(key).label
        chunks.append(f"{label} x{n}")
    return ", ".join(chunks)


def _bluff_risk_reward(scenario: dict, row: dict) -> tuple[float, float]:
    """
    Return (risk, reward) approximation for break-even bluff fold-frequency math.
    """
    pot = float(scenario.get("pot_bb", 0.0))
    to_call = float(scenario.get("to_call_bb", 0.0))
    action = row.get("action")
    size = float(row.get("size_bb") or 0.0)
    if action == "bet":
        return size, max(0.0, pot)
    if action == "raise":
        return max(0.1, size - to_call), max(0.0, pot + to_call)
    return 0.0, max(0.0, pot)


def _hand_blocker_signals(hero_hand: Sequence[str], board: Sequence[str]) -> dict:
    """
    Lightweight blocker diagnostics for coaching text.
    """
    if not hero_hand:
        return {
            "flush_nut_blocker": False,
            "broadway_blockers": 0,
            "paired_board_blockers": 0,
            "signal_text": "No blocker read available.",
        }

    suit_counts: Counter[str] = Counter(card_suit(c) for c in board)
    flush_nut_blocker = False
    flush_draw_suit = None
    for suit, count in suit_counts.items():
        if count >= 3:
            flush_draw_suit = suit
            break

    if flush_draw_suit:
        hero_suited = [c for c in hero_hand if card_suit(c) == flush_draw_suit]
        if hero_suited:
            flush_nut_blocker = any(card_rank(c) >= 13 for c in hero_suited)

    broadway_blockers = sum(1 for c in hero_hand if card_rank(c) >= 10)
    board_rank_counts: Counter[int] = Counter(card_rank(c) for c in board)
    paired_board_blockers = sum(1 for c in hero_hand if board_rank_counts.get(card_rank(c), 0) >= 2)

    notes: List[str] = []
    if flush_nut_blocker:
        notes.append("holds high flush blocker")
    if broadway_blockers >= 2:
        notes.append("double broadway blockers")
    elif broadway_blockers == 1:
        notes.append("single broadway blocker")
    if paired_board_blockers > 0:
        notes.append("blocks full-house combos on paired board")

    return {
        "flush_nut_blocker": flush_nut_blocker,
        "broadway_blockers": broadway_blockers,
        "paired_board_blockers": paired_board_blockers,
        "signal_text": ", ".join(notes) if notes else "blocker profile is neutral",
    }


def _spot_math_snapshot(scenario: dict, chosen: dict) -> dict:
    pot = float(scenario.get("pot_bb", 0.0))
    to_call = float(scenario.get("to_call_bb", 0.0))
    eff = float(scenario.get("effective_stack_bb", 0.0))
    spr = stack_to_pot_ratio(effective_stack=eff, pot_size=max(1.0, pot))
    spr_band = classify_spr(spr)

    required_eq = required_equity_to_call(pot_before_call=pot, call_amount=to_call)
    mdf = minimum_defense_frequency(pot_before_bet=max(0.0, pot - to_call), bet_size=to_call) if to_call > 0 else 1.0

    row_action = str(chosen.get("action", ""))
    row_size = float(chosen.get("size_bb") or 0.0)
    bet_to_pot = row_size / max(1.0, pot) if row_size > 0 else 0.0
    risk, reward = _bluff_risk_reward(scenario, chosen)
    be_fold = break_even_bluff_fold_frequency(risk=risk, reward=reward) if row_size > 0 else 0.0
    bluff_share = polarized_bluff_share(bet_to_pot)
    b_to_v = bluff_to_value_ratio(bet_to_pot)

    return {
        "pot_bb": pot,
        "to_call_bb": to_call,
        "spr": spr,
        "spr_label": spr_band.label,
        "spr_notes": spr_band.notes,
        "required_equity": required_eq,
        "mdf": mdf,
        "bet_to_pot": bet_to_pot,
        "be_bluff_fold_freq": be_fold,
        "target_bluff_share": bluff_share,
        "target_bluff_to_value_ratio": b_to_v,
        "chosen_action": row_action,
        "chosen_size_bb": row_size,
    }


@dataclass
class EquityEstimate:
    equity: float
    stderr: float


class EvCalculator:
    """Compute action EV table for a generated scenario."""

    def __init__(self, scenario: dict, simulations: int = 260):
        self.scenario = scenario
        self.simulations = max(120, min(2400, simulations))
        self.rng = random.Random(int(scenario.get("seed", 1)) + 173)
        self._equity_cache: Dict[Tuple, EquityEstimate] = {}
        self.hero_profile: HeroProfile = parse_hero_profile(scenario.get("hero_profile"))

    @property
    def hero_hand(self) -> List[str]:
        return list(self.scenario["hero_hand"])

    @property
    def board(self) -> List[str]:
        return list(self.scenario["board"])

    @property
    def street(self) -> str:
        return str(self.scenario["street"])

    @property
    def hero_position(self) -> str:
        return str(self.scenario["hero_position"])

    def active_villains(self) -> List[dict]:
        return [
            seat
            for seat in self.scenario["seats"]
            if seat["in_hand"] and not seat["is_hero"]
        ]

    def _equity(
        self,
        villains: Sequence[dict],
        pressure: float,
        samples: Optional[int] = None,
    ) -> EquityEstimate:
        """
        Simulate showdown equity against sampled villain ranges.

        pressure controls range tightening (higher means stronger continue ranges).
        """
        if not villains:
            return EquityEstimate(equity=1.0, stderr=0.0)

        n = samples or self.simulations
        key = (
            tuple(self.hero_hand),
            tuple(self.board),
            self.street,
            tuple((v["archetype_key"], v.get("role", "unknown"), v["position"]) for v in villains),
            round(pressure, 3),
            n,
        )
        if key in self._equity_cache:
            return self._equity_cache[key]

        known_cards = self.hero_hand + self.board
        base_deck = remove_cards(full_deck(), known_cards)
        board_missing = 5 - len(self.board)

        eq_sum = 0.0
        eq_sq_sum = 0.0

        for _ in range(n):
            deck = list(base_deck)
            villain_hands: List[Tuple[str, str]] = []
            valid_sample = True
            for villain in villains:
                archetype = archetype_by_key(villain["archetype_key"])
                hand = sample_villain_hand(
                    deck=deck,
                    board=self.board,
                    street=self.street,
                    archetype=archetype,
                    role=villain.get("role", "unknown"),
                    pressure=pressure,
                    rng=self.rng,
                )
                if hand[0] == hand[1]:
                    valid_sample = False
                    break
                villain_hands.append(hand)
                deck.remove(hand[0])
                deck.remove(hand[1])

            if not valid_sample:
                continue

            runout = self.rng.sample(deck, board_missing) if board_missing > 0 else []
            final_board = self.board + runout
            hero_rank = best_hand_rank(self.hero_hand + final_board)
            villain_ranks = [best_hand_rank(list(vh) + final_board) for vh in villain_hands]

            max_rank = hero_rank
            for rank in villain_ranks:
                if rank > max_rank:
                    max_rank = rank

            if hero_rank == max_rank:
                tied = 1 + sum(1 for rank in villain_ranks if rank == hero_rank)
                share = 1.0 / tied
            else:
                share = 0.0

            eq_sum += share
            eq_sq_sum += share * share

        equity = eq_sum / n
        variance = max(0.0, eq_sq_sum / n - equity * equity)
        stderr = math.sqrt(variance / n)
        out = EquityEstimate(equity=equity, stderr=stderr)
        self._equity_cache[key] = out
        return out

    def _line_realization(self, intent: Optional[str], callers_estimate: float) -> float:
        base = 0.82 + _position_bonus(self.hero_position)
        street_adj = {"preflop": -0.05, "flop": 0.0, "turn": 0.03, "river": 0.06}[self.street]
        intent_adj = 0.0
        if intent == "value":
            intent_adj = 0.08
        elif intent == "bluff":
            intent_adj = -0.08
        multiway_adj = -0.04 * max(0.0, callers_estimate - 1.0)

        # Hero profile adjustments:
        # - Large VPIP-PFR gaps imply weaker line quality in marginal spots.
        # - High AF supports value extraction but can reduce bluff follow-through quality.
        gap_penalty = -max(0.0, self.hero_profile.vpip_pfr_gap - 0.10) * 0.28
        af_bluff_penalty = -max(0.0, self.hero_profile.af - 3.8) * 0.025 if intent == "bluff" else 0.0
        pfr_bonus = max(0.0, self.hero_profile.pfr - 0.20) * 0.08

        return _clamp(
            base + street_adj + intent_adj + multiway_adj + gap_penalty + af_bluff_penalty + pfr_bonus,
            0.45,
            1.05,
        )

    def _hero_image_continue_adjustment(self, intent: str) -> float:
        """
        How villain continue frequency shifts based on hero VPIP/PFR/AF image.
        Positive value means villains continue more.
        """
        image = self.hero_profile.image_bluffiness
        if intent == "bluff":
            return (image - 0.5) * 0.22
        return (image - 0.5) * 0.12

    def _call_like_ev(self, action: str) -> dict:
        pot = float(self.scenario["pot_bb"])
        to_call = float(self.scenario["to_call_bb"])
        villains = self.active_villains()

        equity = self._equity(villains, pressure=0.30)
        realization = self._line_realization(intent=None, callers_estimate=float(len(villains)))
        ff = _future_factor(self.street)

        if action == "check":
            expected_pot = pot * ff
            future_cost = (ff - 1.0) * pot * 0.11
            ev = equity.equity * realization * expected_pot - future_cost
            risk = 0.0
        else:
            expected_pot = (pot + to_call) * ff
            future_cost = (ff - 1.0) * (pot + to_call) * 0.14
            ev = equity.equity * realization * expected_pot - to_call - future_cost
            risk = to_call

        ci = 1.96 * equity.stderr * expected_pot * realization
        return {
            "action": action,
            "size_bb": None,
            "intent": None,
            "label": action.capitalize(),
            "equity": round(equity.equity, 4),
            "fold_equity": 0.0,
            "expected_callers": float(len(villains)),
            "pot_if_called_bb": round(expected_pot, 2),
            "risk_bb": round(risk, 2),
            "realization": round(realization, 3),
            "ev_bb": round(ev, 3),
            "ev_ci_bb": round(ci, 3),
        }

    def _aggressive_ev(self, action: str, size_bb: float, intent: str) -> dict:
        pot = float(self.scenario["pot_bb"])
        to_call = float(self.scenario["to_call_bb"])
        street = self.street
        villains = self.active_villains()

        action_kind = "bet" if action == "bet" else "raise"
        size_ratio = size_bb / max(1.0, pot)
        texture = board_texture_score(self.board)
        texture_adj = 0.0
        if intent == "bluff":
            texture_adj = -0.03 if texture >= 1.5 else 0.03

        hero_image_adj = self._hero_image_continue_adjustment(intent)
        continue_probs = []
        for villain in villains:
            archetype = archetype_by_key(villain["archetype_key"])
            p = continue_probability(
                archetype=archetype,
                street=street,
                action_kind=action_kind,
                size_pot_ratio=size_ratio,
                role=villain.get("role", "unknown"),
            )
            p = _clamp(p + texture_adj + hero_image_adj, 0.03, 0.97)
            continue_probs.append((villain, p))

        p_all_fold = 1.0
        for _, p in continue_probs:
            p_all_fold *= 1.0 - p
        expected_callers = sum(p for _, p in continue_probs)

        target_callers = max(1, min(len(villains), int(round(expected_callers))))
        sorted_by_continue = sorted(continue_probs, key=lambda x: x[1], reverse=True)
        callers_for_equity = [v for v, _ in sorted_by_continue[:target_callers]]
        pressure = _clamp(0.38 + size_ratio * 0.25, 0.25, 0.95)
        equity = self._equity(callers_for_equity, pressure=pressure)

        realization = self._line_realization(intent=intent, callers_estimate=max(1.0, expected_callers))

        if action_kind == "bet":
            pot_if_called = pot + size_bb + expected_callers * size_bb
            risk = size_bb
        else:
            call_delta = max(0.0, size_bb - to_call)
            pot_if_called = pot + size_bb + expected_callers * call_delta
            risk = size_bb

        ev = p_all_fold * pot + (1.0 - p_all_fold) * (
            equity.equity * realization * pot_if_called - risk
        )

        if intent == "value" and equity.equity < 0.45:
            ev -= 0.7
        if intent == "bluff" and equity.equity > 0.58:
            ev -= 0.4

        ci = 1.96 * equity.stderr * pot_if_called * realization
        label_action = "Bet" if action == "bet" else "Raise"
        return {
            "action": action,
            "size_bb": round(size_bb, 2),
            "intent": intent,
            "label": f"{label_action} {size_bb:.1f}bb ({intent.title()})",
            "equity": round(equity.equity, 4),
            "fold_equity": round(p_all_fold, 4),
            "expected_callers": round(expected_callers, 3),
            "pot_if_called_bb": round(pot_if_called, 2),
            "risk_bb": round(risk, 2),
            "realization": round(realization, 3),
            "ev_bb": round(ev, 3),
            "ev_ci_bb": round(ci, 3),
        }

    def action_table(self) -> List[dict]:
        legal = list(self.scenario["legal_actions"])
        table: List[dict] = []

        if "fold" in legal:
            table.append(
                {
                    "action": "fold",
                    "size_bb": None,
                    "intent": None,
                    "label": "Fold",
                    "equity": 0.0,
                    "fold_equity": 0.0,
                    "expected_callers": float(len(self.active_villains())),
                    "pot_if_called_bb": float(self.scenario["pot_bb"]),
                    "risk_bb": 0.0,
                    "realization": 0.0,
                    "ev_bb": 0.0,
                    "ev_ci_bb": 0.0,
                }
            )
        if "check" in legal:
            table.append(self._call_like_ev("check"))
        if "call" in legal:
            table.append(self._call_like_ev("call"))

        if "bet" in legal:
            for size in self.scenario.get("bet_size_options_bb", []):
                for intent in ("value", "bluff"):
                    table.append(self._aggressive_ev("bet", float(size), intent))

        if "raise" in legal:
            for size in self.scenario.get("raise_size_options_bb", []):
                for intent in ("value", "bluff"):
                    table.append(self._aggressive_ev("raise", float(size), intent))

        return sorted(table, key=lambda row: row["ev_bb"], reverse=True)

    def evaluate_choice(self, decision: dict) -> Optional[dict]:
        """
        Compute EV row for exactly one normalized choice.

        This mirrors action_table() row construction and is used for
        counterfactual calculations to avoid recomputing the full table.
        """
        legal = list(self.scenario["legal_actions"])
        action, size, intent = _normalize_choice(decision)
        if action not in legal:
            return None

        if action == "fold":
            return {
                "action": "fold",
                "size_bb": None,
                "intent": None,
                "label": "Fold",
                "equity": 0.0,
                "fold_equity": 0.0,
                "expected_callers": float(len(self.active_villains())),
                "pot_if_called_bb": float(self.scenario["pot_bb"]),
                "risk_bb": 0.0,
                "realization": 0.0,
                "ev_bb": 0.0,
                "ev_ci_bb": 0.0,
            }
        if action == "check":
            return self._call_like_ev("check")
        if action == "call":
            return self._call_like_ev("call")

        if action in {"bet", "raise"}:
            if size is None:
                return None
            if intent is None:
                intent = "value"
            return self._aggressive_ev(action, float(size), str(intent))
        return None


def _find_choice(action_table: List[dict], decision: dict) -> Optional[dict]:
    action, size, intent = _normalize_choice(decision)
    for row in action_table:
        if row["action"] != action:
            continue
        row_size = None if row["size_bb"] is None else round(float(row["size_bb"]), 1)
        if row_size != size:
            continue
        row_intent = None if row["intent"] is None else str(row["intent"]).lower()
        if row_intent != intent:
            continue
        return row
    return None


def _mistake_tags(chosen: dict, best: dict, ev_loss: float) -> List[str]:
    tags: List[str] = []
    if ev_loss < 0.3:
        return tags
    if chosen["action"] == "fold" and best["action"] in {"call", "raise", "bet", "check"}:
        tags.append("Overfold")
    if chosen["intent"] == "bluff" and ev_loss > 0.8:
        tags.append("Overbluff")
    if chosen["intent"] == "value" and chosen["ev_bb"] < 0:
        tags.append("TooThinValue")
    if chosen["action"] in {"call", "check"} and best["action"] in {"raise", "bet"}:
        tags.append("MissedValue")
    if chosen["action"] in {"raise", "bet"} and chosen["intent"] == "value" and best["intent"] == "bluff":
        tags.append("Underbluff")
    return tags


def _decision_from_row(row: dict) -> dict:
    decision = {"action": row["action"]}
    if row.get("size_bb") is not None:
        decision["size_bb"] = float(row["size_bb"])
    if row.get("intent"):
        decision["intent"] = row["intent"]
    return decision


def _hero_profile_analysis(scenario: dict, chosen: Optional[dict] = None, best: Optional[dict] = None) -> dict:
    hero = parse_hero_profile(scenario.get("hero_profile"))
    guidance = hero.position_guidance(scenario["hero_position"], scenario["street"])
    villains = [s for s in scenario["seats"] if s["in_hand"] and not s["is_hero"]]
    street = str(scenario.get("street", "flop"))
    node_type = str(scenario.get("node_type", "single_raised_pot"))
    action_context = str(scenario.get("action_context", "checked_to_hero"))
    players_in_hand = int(scenario.get("players_in_hand", 2))
    texture = board_texture_score(scenario.get("board", []))
    texture_text = _texture_label(texture)
    archetype_mix = _summarize_archetype_mix(villains)
    chosen_row = chosen or {"action": "check", "size_bb": None}
    spot_math = _spot_math_snapshot(scenario, chosen_row)
    blockers = _hand_blocker_signals(scenario.get("hero_hand", []), scenario.get("board", []))

    recommendations: List[str] = []
    low, high = guidance["target_open_vpip_range"]
    if hero.vpip < low - 0.02:
        recommendations.append("VPIP is below positional target; widen in-position opens to avoid passing profitable steals.")
    if hero.vpip > high + 0.06:
        recommendations.append("VPIP is above positional target; prune weakest offsuit opens to reduce dominated postflop nodes.")
    if hero.vpip_pfr_gap > 0.10:
        recommendations.append("VPIP-PFR gap is large: replace marginal flats with more 3-bets/folds to avoid capped ranges.")
    if hero.af > 3.9:
        recommendations.append("AF is very high: cap low-blocker river bluffs and retain more bluff-catchers in your checking range.")
    if hero.fold_to_3bet > 0.65:
        recommendations.append("Fold-to-3bet is high: defend selected suited broadways and pocket pairs to reduce exploitability.")

    if spot_math["to_call_bb"] > 0:
        recommendations.append(
            f"Facing {spot_math['to_call_bb']:.1f}bb, call threshold is {spot_math['required_equity'] * 100:.1f}% equity; "
            f"baseline MDF is {spot_math['mdf'] * 100:.1f}% before exploit adjustments."
        )

    recommendations.append(
        f"SPR is {spot_math['spr']:.1f} ({spot_math['spr_label']}): {spot_math['spr_notes'][0]}"
    )
    if node_type == "single_raised_pot":
        recommendations.append("SRP node: leverage range advantage on favorable boards with disciplined small-to-medium sizings.")
    elif node_type == "three_bet_pot":
        recommendations.append("3-bet pot: tighten bluff density and prioritize blocker quality plus nut-advantage board classes.")
    else:
        recommendations.append("4-bet pot: very range-dense node, so shift toward high-card/blocker-driven decisions and lower pure-bluff frequency.")

    if action_context == "checked_to_hero":
        recommendations.append("Checked-to-hero node: run high-frequency stabs on dry boards, but retain check-back protection on medium-strength holdings.")
    elif action_context == "facing_bet":
        recommendations.append("Facing-bet node: anchor decisions around pot-odds threshold, then adjust exploitively by villain fold/call profile.")
    else:
        recommendations.append("Facing bet+call node: weight value-heavy raises and reduce thin bluffs because at least one range has already continued.")

    if players_in_hand > 2:
        recommendations.append(
            f"Multiway ({players_in_hand} players) and {texture_text} board reduce bluff efficiency; keep bluffs blocker-driven and size-disciplined."
        )
    elif texture_text == "dry":
        recommendations.append("Heads-up on dry texture supports higher small-size stab frequency, especially in position.")
    else:
        recommendations.append(f"{texture_text.title()} texture rewards equity-driven barreling over pure range-denial bluffs.")

    fold_rates = [_street_fold_rate(v["archetype_key"], street) for v in villains]
    avg_fold = sum(fold_rates) / len(fold_rates) if fold_rates else 0.45
    if any(v["archetype_key"] in {"calling_station", "overcaller_preflop"} for v in villains):
        recommendations.append(
            "Pool includes calling-station tendencies: trim air bluffs and shift value sizing upward (about 60-100% pot) with top-pair+ hands."
        )
    if any(v["archetype_key"] in {"nit", "weak_tight", "fit_or_fold", "overfolder_3bet"} for v in villains):
        recommendations.append(
            "Pool includes overfolders: increase frequent small stabs on dry boards and pressure capped ranges on scare-card turns."
        )
    if any(v["archetype_key"] in {"lag_reg", "maniac"} for v in villains):
        recommendations.append(
            "Aggressive villains present: defend more bluff-catchers and avoid low-equity bluff-raises without strong blockers."
        )
    if any(v["archetype_key"] == "trappy" for v in villains):
        recommendations.append(
            "Trappy profiles in pool: reduce auto-barrels on paired boards and protect your checking range with medium-strength value."
        )

    recommendations.append(
        f"Current villain mix ({archetype_mix}) has estimated {street} fold rate of {avg_fold * 100:.1f}%."
    )

    if chosen and chosen.get("action") in {"bet", "raise"}:
        be_fold = spot_math["be_bluff_fold_freq"] * 100
        target_bluff_share = spot_math["target_bluff_share"] * 100
        recommendations.append(
            f"At {spot_math['bet_to_pot']:.2f}x pot sizing, zero-equity bluff needs {be_fold:.1f}% folds; "
            f"polarized bluff share target is {target_bluff_share:.1f}% (ratio {spot_math['target_bluff_to_value_ratio']:.2f}:1)."
        )

    if blockers["signal_text"] != "blocker profile is neutral":
        recommendations.append(f"Blocker read: {blockers['signal_text']}.")
    else:
        recommendations.append("Blocker read is neutral; prioritize line selection by range/nut advantage rather than pure blocker logic.")

    if best and chosen:
        recommendations.append(
            f"Model best line is {best['label']} vs chosen {chosen['label']}; align future selections with that sizing/intent profile in similar nodes."
        )

    return {
        "hero_profile": hero.to_dict(),
        "position_guidance": guidance,
        "recommendations": recommendations[:12],
        "opponent_snapshot": {
            "archetype_mix": archetype_mix,
            "average_street_fold_rate": round(avg_fold, 4),
            "players_in_hand": players_in_hand,
            "texture_label": texture_text,
        },
        "spot_math": {
            "required_equity": round(spot_math["required_equity"], 4),
            "mdf": round(spot_math["mdf"], 4),
            "spr": round(spot_math["spr"], 3),
            "spr_label": spot_math["spr_label"],
        },
    }


def _counterfactual_decision_ev(
    scenario: dict,
    decision: dict,
    simulations: int,
    hero_profile_override: Optional[dict] = None,
    hero_position_override: Optional[str] = None,
) -> float:
    scenario_cf = deepcopy(scenario)
    if hero_profile_override is not None:
        scenario_cf["hero_profile"] = parse_hero_profile(hero_profile_override).to_dict()
    if hero_position_override is not None:
        scenario_cf["hero_position"] = hero_position_override

    calc = EvCalculator(scenario_cf, simulations=simulations)
    row = calc.evaluate_choice(decision)
    if row is None:
        table = calc.action_table()
        row = _find_choice(table, decision)
        if row is None:
            return float("-inf")
    return float(row["ev_bb"])


def _factor_breakdown(
    scenario: dict,
    decision: dict,
    chosen: dict,
    best: dict,
    actions: List[dict],
    simulations: int,
) -> List[dict]:
    ev_loss = max(0.0, float(best["ev_bb"]) - float(chosen["ev_bb"]))
    if ev_loss <= 0.01:
        return []

    chosen_ev = float(chosen["ev_bb"])
    chosen_action = chosen["action"]
    aggressive = chosen_action in {"bet", "raise"}

    raw_factors: List[dict] = []
    spot_math = _spot_math_snapshot(scenario, chosen)
    villains = [s for s in scenario["seats"] if s["in_hand"] and not s["is_hero"]]
    blockers = _hand_blocker_signals(scenario.get("hero_hand", []), scenario.get("board", []))

    same_action_rows = [r for r in actions if r["action"] == chosen_action]
    if same_action_rows:
        best_same_action = max(same_action_rows, key=lambda r: r["ev_bb"])
        action_type_gap = max(0.0, float(best["ev_bb"]) - float(best_same_action["ev_bb"]))
        if action_type_gap > 0.02:
            raw_factors.append(
                {
                    "factor": "Action Choice",
                    "raw_impact_bb": action_type_gap,
                    "detail": (
                        f"Best action class is {best['action']} ({best['ev_bb']:.3f}bb) while chosen class "
                        f"was {chosen_action} (best in-class {best_same_action['ev_bb']:.3f}bb). "
                        "Primary leak is line selection, not just sizing."
                    ),
                }
            )

    if chosen_action == "call" and spot_math["to_call_bb"] > 0:
        required = spot_math["required_equity"]
        eq_gap = max(0.0, required - float(chosen.get("equity", 0.0)))
        if eq_gap > 0.015:
            raw_factors.append(
                {
                    "factor": "Pot Odds Discipline",
                    "raw_impact_bb": eq_gap * (spot_math["pot_bb"] + spot_math["to_call_bb"]) * 0.8,
                    "detail": (
                        f"Call required about {required * 100:.1f}% equity but line had {float(chosen.get('equity', 0.0)) * 100:.1f}%. "
                        "Calling below threshold leaks immediately unless implied odds are strong."
                    ),
                }
            )

    if chosen_action == "fold" and spot_math["to_call_bb"] > 0 and best["action"] in {"call", "raise"}:
        required = spot_math["required_equity"]
        best_eq = float(best.get("equity", 0.0))
        overfold_gap = max(0.0, best_eq - required)
        if overfold_gap > 0.015:
            raw_factors.append(
                {
                    "factor": "Overfold vs Price",
                    "raw_impact_bb": overfold_gap * (spot_math["pot_bb"] + spot_math["to_call_bb"]) * 0.7,
                    "detail": (
                        f"Pot odds asked for {required * 100:.1f}% equity, while stronger continuing lines held about {best_eq * 100:.1f}%. "
                        "Folding surrendered too much defendable equity."
                    ),
                }
            )

    if aggressive:
        same_action_same_intent = [
            r for r in actions if r["action"] == chosen_action and r.get("intent") == chosen.get("intent")
        ]
        if same_action_same_intent:
            best_same_intent = max(same_action_same_intent, key=lambda r: r["ev_bb"])
            sizing_gap = max(0.0, float(best_same_intent["ev_bb"]) - chosen_ev)
            if sizing_gap > 0.02:
                raw_factors.append(
                    {
                        "factor": "Sizing",
                        "raw_impact_bb": sizing_gap,
                        "detail": (
                            f"Within {chosen_action}/{chosen.get('intent')} lines, "
                            f"better sizing existed ({best_same_intent['size_bb']}bb)."
                        ),
                    }
                )

        if chosen.get("size_bb") is not None:
            alt_intent = "value" if chosen.get("intent") == "bluff" else "bluff"
            alt_row = next(
                (
                    r
                    for r in actions
                    if r["action"] == chosen_action
                    and round(float(r.get("size_bb") or 0.0), 1) == round(float(chosen.get("size_bb") or 0.0), 1)
                    and r.get("intent") == alt_intent
                ),
                None,
            )
            if alt_row:
                intent_gap = max(0.0, float(alt_row["ev_bb"]) - chosen_ev)
                if intent_gap > 0.02:
                    raw_factors.append(
                        {
                            "factor": "Value/Bluff Mix",
                            "raw_impact_bb": intent_gap,
                            "detail": (
                                f"For the same size, tagging this line as {alt_intent} "
                                "performed better against these ranges."
                            ),
                        }
                    )

        if chosen.get("intent") == "bluff":
            required_fe = spot_math["be_bluff_fold_freq"]
            achieved_fe = float(chosen.get("fold_equity", 0.0))
            bluff_math_gap = max(0.0, required_fe - achieved_fe)
            if bluff_math_gap > 0.03:
                raw_factors.append(
                    {
                        "factor": "Bluff Economics",
                        "raw_impact_bb": bluff_math_gap * max(0.5, float(chosen.get("risk_bb", 0.0))),
                        "detail": (
                            f"Bluff needed {required_fe * 100:.1f}% folds at this risk/reward, "
                            f"model estimated {achieved_fe * 100:.1f}%."
                        ),
                    }
                )

            if not blockers["flush_nut_blocker"] and blockers["broadway_blockers"] == 0:
                blocker_gap = min(ev_loss * 0.35, 0.22)
                if blocker_gap > 0.02:
                    raw_factors.append(
                        {
                            "factor": "Blocker Quality",
                            "raw_impact_bb": blocker_gap,
                            "detail": (
                                "Bluff line lacked high-card/nut blockers, so villain continues retained too many strong calls."
                            ),
                        }
                    )

    hero = parse_hero_profile(scenario.get("hero_profile"))
    neutral_profile = {
        "vpip": 0.24,
        "pfr": 0.19,
        "af": 2.3,
        "three_bet": 0.08,
        "fold_to_3bet": 0.56,
    }
    counterfactual_sims = max(120, min(220, simulations // 2))
    neutral_ev = _counterfactual_decision_ev(
        scenario=scenario,
        decision=decision,
        simulations=counterfactual_sims,
        hero_profile_override=neutral_profile,
    )
    if math.isfinite(neutral_ev):
        image_gap = max(0.0, neutral_ev - chosen_ev)
        if image_gap > 0.02:
            raw_factors.append(
                {
                    "factor": "Hero Table Image (VPIP/PFR/AF)",
                    "raw_impact_bb": image_gap,
                    "detail": (
                        "Your current profile shifts villain continues versus this line "
                        f"(style={hero.style_label}, image_bluffiness={hero.image_bluffiness:.2f}); "
                        "pool adjusted by calling lighter versus perceived aggression."
                    ),
                }
            )

    if scenario.get("hero_position") != "BTN":
        btn_ev = _counterfactual_decision_ev(
            scenario=scenario,
            decision=decision,
            simulations=counterfactual_sims,
            hero_position_override="BTN",
        )
        if math.isfinite(btn_ev):
            pos_gap = max(0.0, btn_ev - chosen_ev) * 0.7
            if pos_gap > 0.02:
                raw_factors.append(
                    {
                        "factor": "Position Leverage",
                        "raw_impact_bb": pos_gap,
                        "detail": (
                            f"Same line as BTN estimated {btn_ev:.3f}bb versus {chosen_ev:.3f}bb here; "
                            "OOP realization and check-back denial reduced EV."
                        ),
                    }
                )

    players_in_hand = int(scenario.get("players_in_hand", 2))
    if players_in_hand > 2 and aggressive and chosen.get("intent") == "bluff":
        size_ratio = float(chosen.get("size_bb") or 0.0) / max(1.0, float(scenario.get("pot_bb", 1.0)))
        multiway_gap = (players_in_hand - 2) * (0.12 + 0.18 * size_ratio)
        multiway_gap = min(multiway_gap, ev_loss * 0.8)
        if multiway_gap > 0.02:
            raw_factors.append(
                {
                    "factor": "Multiway Bluff Penalty",
                    "raw_impact_bb": multiway_gap,
                    "detail": (
                        f"{players_in_hand}-way node reduced fold-chain reliability; "
                        "multiway bluffs require stronger blocker/equity backup than heads-up nodes."
                    ),
                }
            )

    if villains:
        street = str(scenario.get("street", "flop"))
        fold_rates = [_street_fold_rate(villain["archetype_key"], street) for villain in villains]
        avg_fold = sum(fold_rates) / max(1, len(fold_rates))
        archetype_mix = _summarize_archetype_mix(villains)

        exploit_gap = 0.0
        detail = ""
        if chosen.get("intent") == "bluff":
            exploit_gap = max(0.0, 0.44 - avg_fold) * 2.1
            detail = (
                f"Pool ({archetype_mix}) folds too little on {street} (avg {avg_fold:.2f}) "
                "for this bluff frequency/size."
            )
        elif chosen.get("intent") == "value":
            exploit_gap = max(0.0, avg_fold - 0.60) * 1.2
            detail = (
                f"Pool ({archetype_mix}) folds often (avg {avg_fold:.2f}); "
                "value line likely needed smaller sizing or stronger value density."
            )
        if exploit_gap > 0.02:
            raw_factors.append(
                {
                    "factor": "Opponent Archetype Mismatch",
                    "raw_impact_bb": exploit_gap,
                    "detail": detail,
                }
            )

    texture = board_texture_score(scenario.get("board", []))
    if chosen.get("intent") == "bluff" and texture >= 1.4:
        texture_gap = min(ev_loss * 0.4, 0.18 * texture)
        if texture_gap > 0.02:
            raw_factors.append(
                {
                    "factor": "Board Texture",
                    "raw_impact_bb": texture_gap,
                    "detail": (
                        f"{_texture_label(texture).title()} texture ({texture:.2f}) lowers fold equity and "
                        "increases natural continues from pair+draw holdings."
                    ),
                }
            )

    if spot_math["spr"] >= 8.0 and aggressive and chosen.get("intent") == "bluff":
        spr_gap = min(ev_loss * 0.35, 0.24)
        if spr_gap > 0.02:
            raw_factors.append(
                {
                    "factor": "SPR Planning",
                    "raw_impact_bb": spr_gap,
                    "detail": (
                        f"High SPR ({spot_math['spr']:.1f}) rewards nutted potential and selective aggression; "
                        "line over-committed medium equity."
                    ),
                }
            )

    if not raw_factors:
        return []

    total_raw = sum(f["raw_impact_bb"] for f in raw_factors)
    if total_raw <= 0:
        return []

    scale = ev_loss / total_raw
    factors = []
    remaining = ev_loss
    for factor in sorted(raw_factors, key=lambda f: f["raw_impact_bb"], reverse=True):
        impact = round(factor["raw_impact_bb"] * scale, 3)
        impact = min(impact, round(max(0.0, remaining), 3))
        remaining = round(max(0.0, remaining - impact), 3)
        factors.append(
            {
                "factor": factor["factor"],
                "impact_bb": impact,
                "share_pct": round((impact / ev_loss) * 100.0, 1) if ev_loss > 0 else 0.0,
                "detail": factor["detail"],
            }
        )

    if remaining > 0.04:
        factors.append(
            {
                "factor": "Residual/Model Uncertainty",
                "impact_bb": round(remaining, 3),
                "share_pct": round((remaining / ev_loss) * 100.0, 1),
                "detail": "Remaining gap from interactions between factors and simulation variance.",
            }
        )

    return factors


def _build_leak_report(
    scenario: dict,
    decision: dict,
    chosen: dict,
    best: dict,
    actions: List[dict],
    ev_loss: float,
    simulations: int,
) -> dict:
    spot_math = _spot_math_snapshot(scenario, chosen)
    texture = board_texture_score(scenario.get("board", []))
    villains = [s for s in scenario["seats"] if s["in_hand"] and not s["is_hero"]]
    archetype_mix = _summarize_archetype_mix(villains)
    factor_breakdown = _factor_breakdown(
        scenario=scenario,
        decision=decision,
        chosen=chosen,
        best=best,
        actions=actions,
        simulations=simulations,
    )
    top_factor = factor_breakdown[0]["factor"] if factor_breakdown else "No significant leak factors"
    summary = (
        f"EV leak {ev_loss:.3f}bb in {scenario['street']} {scenario['hero_position']} spot "
        f"({scenario['players_in_hand']}-way, SPR {spot_math['spr']:.1f}, {_texture_label(texture)} board). "
        f"Pot-odds equity threshold {spot_math['required_equity'] * 100:.1f}%, baseline MDF {spot_math['mdf'] * 100:.1f}%. "
        f"Best line: {best['label']} ({best['ev_bb']:.3f}bb) vs chosen {chosen['label']} ({chosen['ev_bb']:.3f}bb). "
        f"Primary driver: {top_factor}. Pool: {archetype_mix}."
    )
    return {
        "summary": summary,
        "optimal_gap_bb": round(ev_loss, 3),
        "factor_breakdown": factor_breakdown,
        "hero_profile_analysis": _hero_profile_analysis(scenario, chosen=chosen, best=best),
    }


def evaluate_decision(
    scenario: dict,
    decision: dict,
    simulations: int = 260,
    precomputed_actions: Optional[List[dict]] = None,
) -> dict:
    """Return EV table, score, and leak explanation for one decision."""
    if precomputed_actions is not None:
        actions = list(precomputed_actions)
    else:
        calc = EvCalculator(scenario, simulations=simulations)
        actions = calc.action_table()
    if not actions:
        raise ValueError("No legal actions were generated for this scenario")

    best = actions[0]
    chosen = _find_choice(actions, decision)
    if chosen is None:
        normalized = _normalize_choice(decision)
        raise ValueError(
            f"Chosen action not found in legal action table: {normalized}. "
            "Ensure size and intent are selected for bet/raise."
        )

    ev_loss = round(float(best["ev_bb"]) - float(chosen["ev_bb"]), 3)
    verdict = "Excellent"
    if ev_loss > 0.2:
        verdict = "Good"
    if ev_loss > 0.8:
        verdict = "Leak"
    if ev_loss > 1.6:
        verdict = "Major Leak"

    return {
        "scenario_id": scenario["scenario_id"],
        "best_action": best,
        "chosen_action": chosen,
        "ev_loss_bb": ev_loss,
        "verdict": verdict,
        "mistake_tags": _mistake_tags(chosen, best, ev_loss),
        "action_table": actions,
        "leak_report": _build_leak_report(
            scenario=scenario,
            decision=decision,
            chosen=chosen,
            best=best,
            actions=actions,
            ev_loss=ev_loss,
            simulations=simulations,
        ),
    }
