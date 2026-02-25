"""Interactive heads-up live-play simulator against profile-based opponents."""

from __future__ import annotations

import itertools
import math
import random
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from trainer.cards import (
    best_hand_rank,
    board_texture_score,
    card_rank,
    card_suit,
    full_deck,
    preflop_strength_score,
    rank_category_name,
    remove_cards,
)
from trainer.constants import BET_SIZE_PCTS
from trainer.scenario import generate_scenario


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _rate(value: float, default: float) -> float:
    if value is None:
        return default
    out = float(value)
    if out > 1.0:
        out /= 100.0
    return _clamp(out, 0.0, 1.0)


def _round1(value: float) -> float:
    return round(max(0.0, float(value)), 1)


def _street_board_count(street: str) -> int:
    return {"preflop": 0, "flop": 3, "turn": 4, "river": 5}[street]


def _next_street(street: str) -> Optional[str]:
    order = ["preflop", "flop", "turn", "river"]
    idx = order.index(street)
    if idx + 1 >= len(order):
        return None
    return order[idx + 1]


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _canonical_combo(cards: List[str] | tuple[str, str]) -> tuple[str, str]:
    a, b = cards[0], cards[1]
    if a < b:
        return (a, b)
    return (b, a)


def _combo_key(cards: List[str] | tuple[str, str]) -> str:
    c1, c2 = cards[0], cards[1]
    r1 = c1[0]
    r2 = c2[0]
    v1 = card_rank(c1)
    v2 = card_rank(c2)
    if v2 > v1:
        r1, r2 = r2, r1
        c1, c2 = c2, c1
    if r1 == r2:
        return f"{r1}{r2}"
    suited = card_suit(c1) == card_suit(c2)
    return f"{r1}{r2}{'s' if suited else 'o'}"


def _normalize_distribution(weights: Dict[str, float]) -> Dict[str, float]:
    total = sum(max(0.0, v) for v in weights.values())
    if total <= 0:
        n = max(1, len(weights))
        return {k: 1.0 / n for k in weights}
    return {k: max(0.0, v) / total for k, v in weights.items()}


@dataclass
class OpponentProfile:
    """Normalized opponent profile used by live-play decision logic."""

    name: str
    style_label: str = "Unknown"
    source: str = "custom"
    hands_analyzed: int = 0
    vpip: float = 0.32
    pfr: float = 0.21
    three_bet: float = 0.08
    fold_to_3bet: float = 0.45
    limp_rate: float = 0.12
    af: float = 2.2
    aggression_frequency: float = 0.38
    flop_cbet: float = 0.58
    turn_cbet: float = 0.44
    river_cbet: float = 0.32
    check_raise: float = 0.09
    wtsd: float = 0.30
    w_sd: float = 0.51
    tendencies: List[str] = field(default_factory=list)
    exploits: List[dict] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict) -> "OpponentProfile":
        raw = raw or {}
        return cls(
            name=str(raw.get("name", "Villain")),
            style_label=str(raw.get("style_label", raw.get("style", "Unknown"))),
            source=str(raw.get("source", "custom")),
            hands_analyzed=int(raw.get("hands_analyzed", 0) or 0),
            vpip=_rate(raw.get("vpip"), 0.32),
            pfr=_rate(raw.get("pfr"), 0.21),
            three_bet=_rate(raw.get("three_bet"), 0.08),
            fold_to_3bet=_rate(raw.get("fold_to_3bet"), 0.45),
            limp_rate=_rate(raw.get("limp_rate"), 0.12),
            af=_clamp(float(raw.get("af", 2.2)), 0.3, 8.0),
            aggression_frequency=_rate(raw.get("aggression_frequency"), 0.38),
            flop_cbet=_rate(raw.get("flop_cbet"), 0.58),
            turn_cbet=_rate(raw.get("turn_cbet"), 0.44),
            river_cbet=_rate(raw.get("river_cbet"), 0.32),
            check_raise=_rate(raw.get("check_raise"), 0.09),
            wtsd=_rate(raw.get("wtsd"), 0.30),
            w_sd=_rate(raw.get("w_sd"), 0.51),
            tendencies=list(raw.get("tendencies", [])),
            exploits=list(raw.get("exploits", [])),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "style_label": self.style_label,
            "source": self.source,
            "hands_analyzed": self.hands_analyzed,
            "vpip": round(self.vpip, 4),
            "pfr": round(self.pfr, 4),
            "three_bet": round(self.three_bet, 4),
            "fold_to_3bet": round(self.fold_to_3bet, 4),
            "limp_rate": round(self.limp_rate, 4),
            "af": round(self.af, 3),
            "aggression_frequency": round(self.aggression_frequency, 4),
            "flop_cbet": round(self.flop_cbet, 4),
            "turn_cbet": round(self.turn_cbet, 4),
            "river_cbet": round(self.river_cbet, 4),
            "check_raise": round(self.check_raise, 4),
            "wtsd": round(self.wtsd, 4),
            "w_sd": round(self.w_sd, 4),
            "tendencies": self.tendencies,
            "exploits": self.exploits,
        }


@dataclass
class LiveHand:
    """One simulated hand in an interactive session."""

    hand_no: int
    mode: str
    hero_position: str
    button_on_hero: bool
    street: str
    board: List[str]
    full_board: List[str]
    hero_hand: List[str]
    villain_hand: List[str]
    pot_bb: float
    to_call_bb: float
    action_context: str
    legal_actions: List[str]
    size_options_bb: List[float]
    action_history: List[str]
    hero_remaining_bb: float
    villain_remaining_bb: float
    hero_invested_bb: float
    villain_invested_bb: float
    preflop_aggressor: str = "none"
    hero_first_this_street: bool = False
    hero_phase: str = "initial"
    node_type: str = "single_raised_pot"
    hand_over: bool = False
    hero_delta_bb: float = 0.0
    showdown: Optional[dict] = None
    villain_range_summary: dict = field(default_factory=dict)

    def to_public(self) -> dict:
        out = {
            "hand_no": self.hand_no,
            "mode": self.mode,
            "hero_position": self.hero_position,
            "street": self.street,
            "board": list(self.board),
            "hero_hand": list(self.hero_hand),
            "pot_bb": round(self.pot_bb, 2),
            "to_call_bb": round(self.to_call_bb, 2),
            "action_context": self.action_context,
            "legal_actions": list(self.legal_actions),
            "size_options_bb": [round(v, 1) for v in self.size_options_bb],
            "action_history": list(self.action_history),
            "hand_over": self.hand_over,
            "hero_delta_bb": round(self.hero_delta_bb, 3),
            "villain_range_summary": dict(self.villain_range_summary or {}),
        }
        if self.hand_over:
            out["villain_hand"] = list(self.villain_hand)
            out["showdown"] = self.showdown
        return out


class LiveMatch:
    """Stateful interactive heads-up match."""

    def __init__(
        self,
        opponent_profile: dict,
        seed: Optional[int] = None,
        starting_stack_bb: float = 100.0,
        sb: float = 1.0,
        bb: float = 2.0,
        mode: str = "full_game",
        target_config: Optional[dict] = None,
    ):
        self.session_id = f"live_{uuid.uuid4().hex[:12]}"
        self.seed = int(seed or random.randint(1, 10_000_000))
        self.rng = random.Random(self.seed)
        self.opponent = OpponentProfile.from_dict(opponent_profile)
        self.starting_stack_bb = _clamp(float(starting_stack_bb), 20.0, 400.0)
        self.sb = _clamp(float(sb), 0.1, 10.0)
        self.bb = _clamp(float(bb), self.sb + 0.1, 20.0)
        self.mode = "targeted" if mode == "targeted" else "full_game"
        self.target_config = dict(target_config or {})
        self.hands_played = 0
        self.hero_net_bb = 0.0
        self._button_on_hero = True
        self._hero_stats = {
            "total_actions": 0,
            "aggressive_actions": 0,
            "bets": 0,
            "raises": 0,
            "calls": 0,
            "checks": 0,
            "folds": 0,
            "declared_bluffs": 0,
            "aggr_size_to_pot_sum": 0.0,
            "aggr_size_samples": 0,
            "recent_aggr_flags": [],
        }
        self.current_hand: Optional[LiveHand] = None
        self._range_entries: List[dict] = []
        self._range_index: Dict[tuple[str, str], dict] = {}
        self._range_adherence_value: float = 0.65
        self.start_next_hand()

    def state(self) -> dict:
        if self.current_hand is None:
            raise ValueError("No active hand")
        return {
            "session_id": self.session_id,
            "seed": self.seed,
            "match": {
                "hands_played": self.hands_played,
                "hero_net_bb": round(self.hero_net_bb, 3),
                "mode": self.mode,
                "opponent": self.opponent.to_dict(),
            },
            "hand": self.current_hand.to_public(),
        }

    def start_next_hand(self) -> dict:
        self.hands_played += 1
        if self.mode == "targeted":
            self.current_hand = self._build_targeted_hand()
        else:
            self.current_hand = self._build_full_hand()
        return self.state()

    def hero_action(self, action: str, size_bb: Optional[float] = None, intent: Optional[str] = None) -> dict:
        if self.current_hand is None:
            raise ValueError("No active hand")
        hand = self.current_hand
        if hand.hand_over:
            raise ValueError("Hand is complete. Start next hand.")

        act = str(action or "").lower()
        if act not in hand.legal_actions:
            raise ValueError(f"Illegal action: {act}")

        if act in {"bet", "raise"}:
            if size_bb is None:
                raise ValueError("size_bb is required for bet/raise")
            size_bb = float(size_bb)
            if size_bb <= 0:
                raise ValueError("size_bb must be positive")
            if hand.size_options_bb:
                nearest = min(hand.size_options_bb, key=lambda v: abs(v - size_bb))
                size_bb = nearest

        self._record_hero_action(action=act, size_bb=size_bb, intent=intent)

        if act == "fold":
            hand.action_history.append("Hero folds.")
            self._end_by_fold(winner="villain", reason="Hero folded.")
            return self.state()

        if act == "call":
            commit = self._hero_commit(hand.to_call_bb)
            hand.action_history.append(f"Hero calls {commit:.1f}bb.")
            hand.to_call_bb = 0.0
            if self._is_all_in():
                self._resolve_showdown()
            else:
                self._advance_street()
            return self.state()

        if act == "check":
            hand.action_history.append("Hero checks.")
            if hand.hero_first_this_street and hand.hero_phase == "initial":
                self._villain_after_hero_check()
            else:
                self._advance_street()
            return self.state()

        if act == "bet":
            commit = self._hero_commit(size_bb or 0.0)
            hand.action_history.append(f"Hero bets {commit:.1f}bb ({(intent or 'value').lower()}).")
            self._set_preflop_aggressor("hero")
            self._villain_response_to_hero_aggression(hero_action_amount=commit, previous_to_call=0.0, is_raise=False)
            return self.state()

        if act == "raise":
            prev_to_call = hand.to_call_bb
            commit = self._hero_commit(size_bb or 0.0)
            hand.action_history.append(f"Hero raises {commit:.1f}bb ({(intent or 'value').lower()}).")
            self._set_preflop_aggressor("hero")
            self._villain_response_to_hero_aggression(
                hero_action_amount=commit,
                previous_to_call=prev_to_call,
                is_raise=True,
            )
            return self.state()

        raise ValueError(f"Unhandled action: {act}")

    def _build_full_hand(self) -> LiveHand:
        self._button_on_hero = bool(self.hands_played % 2 == 1)
        hero_position = "BTN" if self._button_on_hero else "BB"

        deck = full_deck()
        hero_hand = self.rng.sample(deck, 2)
        for c in hero_hand:
            deck.remove(c)
        villain_hand = self.rng.sample(deck, 2)
        for c in villain_hand:
            deck.remove(c)
        full_board = self.rng.sample(deck, 5)

        hand = LiveHand(
            hand_no=self.hands_played,
            mode="full_game",
            hero_position=hero_position,
            button_on_hero=self._button_on_hero,
            street="preflop",
            board=[],
            full_board=full_board,
            hero_hand=hero_hand,
            villain_hand=villain_hand,
            pot_bb=0.0,
            to_call_bb=0.0,
            action_context="checked_to_hero",
            legal_actions=[],
            size_options_bb=[],
            action_history=[],
            hero_remaining_bb=self.starting_stack_bb,
            villain_remaining_bb=self.starting_stack_bb,
            hero_invested_bb=0.0,
            villain_invested_bb=0.0,
            preflop_aggressor="none",
            hero_first_this_street=self._hero_first_on_street("preflop"),
            hero_phase="initial",
            node_type="single_raised_pot",
        )
        self.current_hand = hand
        self._init_range_model()
        hand.action_history.append(
            f"Hand {hand.hand_no}: Hero ({hero_position}) vs {self.opponent.name} ({self.opponent.style_label})."
        )

        if self._button_on_hero:
            hero_sb = self._hero_commit(self.sb)
            villain_bb = self._villain_commit(self.bb)
            hand.action_history.append(f"Hero posts SB {hero_sb:.1f}bb.")
            hand.action_history.append(f"Villain posts BB {villain_bb:.1f}bb.")
            hand.to_call_bb = _round1(max(0.0, self.bb - self.sb))
            hand.action_context = "facing_bet"
        else:
            villain_sb = self._villain_commit(self.sb)
            hero_bb = self._hero_commit(self.bb)
            hand.action_history.append(f"Villain posts SB {villain_sb:.1f}bb.")
            hand.action_history.append(f"Hero posts BB {hero_bb:.1f}bb.")
            self._villain_preflop_first_action()

        if not hand.hand_over:
            self._update_legal_options()
        return hand

    def _build_targeted_hand(self) -> LiveHand:
        payload = dict(self.target_config or {})
        payload["num_players"] = 2
        payload["players_in_hand"] = 2
        payload["equal_stacks"] = True
        payload["default_stack_bb"] = self.starting_stack_bb
        payload["sb"] = self.sb
        payload["bb"] = self.bb
        payload["seed"] = self.rng.randint(1, 10_000_000)
        payload.setdefault("street", "flop")
        payload.setdefault("node_type", "single_raised_pot")
        payload.setdefault("action_context", "facing_bet")
        payload.setdefault("hero_position", "BTN")

        scenario = generate_scenario(payload)
        deck = remove_cards(full_deck(), scenario["hero_hand"] + scenario["board"])
        villain_hand = self.rng.sample(deck, 2)
        for c in villain_hand:
            deck.remove(c)
        full_board = list(scenario["board"])
        if len(full_board) < 5:
            full_board.extend(self.rng.sample(deck, 5 - len(full_board)))

        hero_position = str(scenario["hero_position"])
        hand = LiveHand(
            hand_no=self.hands_played,
            mode="targeted",
            hero_position=hero_position,
            button_on_hero=(hero_position == "BTN"),
            street=str(scenario["street"]),
            board=list(scenario["board"]),
            full_board=full_board,
            hero_hand=list(scenario["hero_hand"]),
            villain_hand=villain_hand,
            pot_bb=float(scenario["pot_bb"]),
            to_call_bb=float(scenario["to_call_bb"]),
            action_context=str(scenario["action_context"]),
            legal_actions=list(scenario["legal_actions"]),
            size_options_bb=list(scenario.get("raise_size_options_bb", []) or scenario.get("bet_size_options_bb", [])),
            action_history=list(scenario.get("action_history", [])),
            hero_remaining_bb=max(0.0, self.starting_stack_bb - float(scenario["pot_bb"]) / 2.0),
            villain_remaining_bb=max(0.0, self.starting_stack_bb - float(scenario["pot_bb"]) / 2.0),
            hero_invested_bb=float(scenario["pot_bb"]) / 2.0,
            villain_invested_bb=float(scenario["pot_bb"]) / 2.0,
            preflop_aggressor="unknown",
            hero_first_this_street=self._hero_first_on_street(str(scenario["street"]), hero_position == "BTN"),
            hero_phase="initial",
            node_type=str(scenario.get("node_type", "single_raised_pot")),
        )
        self.current_hand = hand
        self._init_range_model()
        hand.action_history.append(f"Targeted spot loaded vs {self.opponent.name}.")
        self._update_legal_options()
        return hand

    def _hero_first_on_street(self, street: str, button_on_hero: Optional[bool] = None) -> bool:
        button = self._button_on_hero if button_on_hero is None else button_on_hero
        if street == "preflop":
            return button
        return not button

    def _record_hero_action(self, action: str, size_bb: Optional[float], intent: Optional[str]) -> None:
        hand = self.current_hand
        if hand is None:
            return
        action = str(action or "").lower()
        stats = self._hero_stats
        stats["total_actions"] += 1

        is_aggr = action in {"bet", "raise"}
        if is_aggr:
            stats["aggressive_actions"] += 1
            if action == "bet":
                stats["bets"] += 1
            else:
                stats["raises"] += 1
            if str(intent or "").lower() == "bluff":
                stats["declared_bluffs"] += 1
            if size_bb is not None:
                pot = max(1.0, float(hand.pot_bb))
                size_ratio = float(size_bb) / pot
                stats["aggr_size_to_pot_sum"] += _clamp(size_ratio, 0.0, 3.0)
                stats["aggr_size_samples"] += 1
        elif action == "call":
            stats["calls"] += 1
        elif action == "check":
            stats["checks"] += 1
        elif action == "fold":
            stats["folds"] += 1

        recent = stats["recent_aggr_flags"]
        recent.append(1 if is_aggr else 0)
        if len(recent) > 12:
            del recent[0]

    def _hero_image_score(self) -> float:
        """0..1 perceived hero aggression/bluffiness based on observed actions."""
        stats = self._hero_stats
        total = max(1, int(stats["total_actions"]))
        aggr = int(stats["aggressive_actions"])
        agg_rate = aggr / total
        raise_rate = int(stats["raises"]) / total
        bluff_rate = int(stats["declared_bluffs"]) / max(1, aggr)
        avg_size = float(stats["aggr_size_to_pot_sum"]) / max(1, int(stats["aggr_size_samples"]))
        recent = stats["recent_aggr_flags"]
        recent_rate = sum(recent) / max(1, len(recent))

        score = (
            0.24
            + agg_rate * 0.36
            + raise_rate * 0.14
            + bluff_rate * 0.14
            + _clamp(avg_size, 0.0, 2.0) * 0.08
            + recent_rate * 0.10
        )
        return _clamp(score, 0.05, 0.95)

    def _range_adherence(self) -> float:
        """How closely villain follows stat-derived ranges instead of random deviations."""
        gap = max(0.0, self.opponent.vpip - self.opponent.pfr)
        af_over = max(0.0, self.opponent.af - 2.3)
        passive_bonus = max(0.0, 1.9 - self.opponent.af) * 0.05
        base = 0.84 - gap * 0.58 - af_over * 0.08 + passive_bonus
        style = self.opponent.style_label.lower()
        if "calling station" in style or "loose-passive" in style:
            base -= 0.06
        if "tag" in style:
            base += 0.05
        return _clamp(base, 0.35, 0.93)

    def _init_range_model(self) -> None:
        hand = self.current_hand
        if hand is None:
            return
        known_cards = hand.hero_hand + hand.board
        deck = remove_cards(full_deck(), known_cards)
        combos = list(itertools.combinations(deck, 2))
        if not combos:
            self._range_entries = []
            self._range_index = {}
            hand.villain_range_summary = {}
            return

        scored = []
        for combo in combos:
            pre_score = preflop_strength_score(combo[0], combo[1]) / 100.0
            scored.append((combo, pre_score))
        scored.sort(key=lambda x: x[1], reverse=True)

        n = len(scored)
        vpip_rate = _clamp(self.opponent.vpip + 0.02, 0.08, 0.94)
        pfr_rate = _clamp(self.opponent.pfr + self.opponent.three_bet * 0.30, 0.04, 0.82)
        three_rate = _clamp(self.opponent.three_bet * 2.2, 0.02, 0.50)
        limp_bias = _clamp(self.opponent.limp_rate * 0.7, 0.0, 0.55)

        entries: List[dict] = []
        for idx, (combo, pre_score) in enumerate(scored):
            strength_q = 1.0 - (idx / max(1, n - 1))
            play_prob = _clamp(_sigmoid((strength_q - (1.0 - vpip_rate)) / 0.09), 0.001, 0.999)
            raise_prob = _clamp(_sigmoid((strength_q - (1.0 - pfr_rate)) / 0.08), 0.001, 0.995)
            threebet_prob = _clamp(_sigmoid((strength_q - (1.0 - three_rate)) / 0.07), 0.001, 0.92)
            call_prob = _clamp(play_prob - raise_prob * (0.80 - limp_bias * 0.2) + limp_bias * 0.06, 0.001, 0.995)
            entry = {
                "cards": _canonical_combo(combo),
                "key": _combo_key(combo),
                "pre_score": pre_score,
                "strength_q": strength_q,
                "play_prob": play_prob,
                "raise_prob": raise_prob,
                "call_prob": call_prob,
                "threebet_prob": threebet_prob,
                "weight": play_prob,
            }
            entries.append(entry)

        total = sum(e["weight"] for e in entries)
        if total > 0:
            for e in entries:
                e["weight"] /= total

        self._range_entries = entries
        self._range_index = {e["cards"]: e for e in entries}
        self._range_adherence_value = self._range_adherence()
        self._refresh_range_summary(event="range_seeded")

    def _combo_draw_strength(self, combo_cards: tuple[str, str], board: List[str]) -> float:
        if len(board) < 3:
            return 0.0
        cards = list(combo_cards) + list(board)

        suit_counts: Dict[str, int] = {}
        board_suits: Dict[str, int] = {}
        for c in cards:
            s = card_suit(c)
            suit_counts[s] = suit_counts.get(s, 0) + 1
        for c in board:
            s = card_suit(c)
            board_suits[s] = board_suits.get(s, 0) + 1
        max_suit = max(suit_counts.values())
        flush_draw = 0.0
        if len(board) < 5:
            for s, count in suit_counts.items():
                if count >= 4 and board_suits.get(s, 0) >= 2:
                    flush_draw = 0.26
                    break

        ranks = sorted({card_rank(c) for c in cards})
        if 14 in ranks:
            ranks.append(1)
        best_run = 1
        run = 1
        for i in range(1, len(ranks)):
            if ranks[i] == ranks[i - 1] + 1:
                run += 1
                best_run = max(best_run, run)
            elif ranks[i] != ranks[i - 1]:
                run = 1
        straight_draw = 0.0
        if len(board) < 5:
            if best_run >= 4:
                straight_draw = 0.25
            elif best_run == 3:
                straight_draw = 0.12

        overcard_bonus = 0.0
        if len(board) == 3:
            board_high = max(card_rank(c) for c in board)
            overcards = sum(1 for c in combo_cards if card_rank(c) > board_high)
            overcard_bonus = overcards * 0.06

        return _clamp(flush_draw + straight_draw + overcard_bonus, 0.0, 0.75)

    def _combo_postflop_strength(self, combo_cards: tuple[str, str], board: List[str], street: str) -> float:
        if street == "preflop":
            return _clamp(preflop_strength_score(combo_cards[0], combo_cards[1]) / 100.0, 0.0, 1.0)
        if len(board) < 3:
            return _clamp(preflop_strength_score(combo_cards[0], combo_cards[1]) / 100.0, 0.0, 1.0)
        rank = best_hand_rank(list(combo_cards) + list(board))
        category = rank[0] / 8.0
        kicker = rank[1][0] / 14.0 if rank[1] else 0.0
        draw = self._combo_draw_strength(combo_cards, board)
        return _clamp(category * 0.80 + kicker * 0.11 + draw * 0.42, 0.0, 1.35)

    def _combo_action_probability(
        self,
        entry: dict,
        action: str,
        call_amount: float,
        hero_checked: bool,
        is_raise: bool,
    ) -> float:
        hand = self.current_hand
        if hand is None:
            return 0.1
        street = hand.street
        action = str(action)
        call_amount = max(0.0, float(call_amount))
        hero_image = self._hero_image_score()
        hero_image_adj = hero_image - 0.5

        if street == "preflop":
            play_prob = entry.get("play_prob", 0.35)
            raise_prob = entry.get("raise_prob", 0.18)
            call_prob = entry.get("call_prob", 0.20)
            threebet_prob = entry.get("threebet_prob", 0.08)
            if action == "fold":
                fold_p = 1.0 - play_prob
                if call_amount > 0:
                    fold_p -= hero_image_adj * (0.15 + max(0.0, self.opponent.vpip - self.opponent.pfr) * 0.18)
                return _clamp(fold_p, 0.001, 0.995)
            if action == "raise":
                base_raise = raise_prob
                if is_raise:
                    base_raise = _clamp(threebet_prob + self.opponent.three_bet * 0.32 + raise_prob * 0.24, 0.01, 0.95)
                    base_raise += hero_image_adj * 0.06
                return _clamp(base_raise, 0.001, 0.95)
            if action == "call":
                cp = call_prob * (1.0 + self.opponent.limp_rate * 0.25)
                if call_amount > 0:
                    cp += hero_image_adj * (0.12 + max(0.0, self.opponent.vpip - self.opponent.pfr) * 0.28)
                return _clamp(cp, 0.001, 0.95)
            if action == "check":
                return _clamp(call_prob + (1.0 - play_prob) * 0.45, 0.001, 0.95)
            return 0.01

        board = hand.board
        pot = max(1.0, hand.pot_bb)
        draw = self._combo_draw_strength(entry["cards"], board)
        strength = self._combo_postflop_strength(entry["cards"], board, street)
        texture = board_texture_score(board)

        if street == "flop":
            street_base = self.opponent.flop_cbet
        elif street == "turn":
            street_base = self.opponent.turn_cbet
        else:
            street_base = self.opponent.river_cbet

        bet_prob = (
            street_base * 0.40
            + self.opponent.aggression_frequency * 0.24
            + strength * 0.42
            + draw * 0.20
            - self.opponent.wtsd * 0.10
            - texture * (0.02 if street in {"turn", "river"} else 0.0)
        )
        bet_prob -= hero_image_adj * 0.06
        if hero_checked:
            bet_prob += 0.10
        bet_prob = _clamp(bet_prob, 0.01, 0.98)

        if action == "check":
            return _clamp(1.0 - bet_prob, 0.01, 0.98)
        if action == "bet":
            return _clamp(bet_prob, 0.01, 0.98)

        if action in {"call", "fold", "raise"}:
            required_equity = call_amount / max(1.0, pot + call_amount)
            eq_proxy = _clamp(0.12 + strength * 0.66 + draw * 0.22, 0.0, 0.99)
            continue_prob = _sigmoid((eq_proxy - required_equity) / 0.11)
            station_adj = (self.opponent.wtsd - 0.30) * 0.38 + (self.opponent.vpip - self.opponent.pfr) * 0.52
            hero_image_continue = hero_image_adj * (
                0.20 + max(0.0, self.opponent.vpip - self.opponent.pfr) * 0.34 + self.opponent.wtsd * 0.22
            )
            continue_prob = _clamp(continue_prob + station_adj, 0.01, 0.99)
            continue_prob = _clamp(continue_prob + hero_image_continue, 0.01, 0.99)
            raise_share = _clamp(
                self.opponent.check_raise * 0.75 + max(0.0, self.opponent.af - 2.5) * 0.07 + max(0.0, strength - 0.80) * 0.30,
                0.01,
                0.55,
            )
            if action == "raise":
                return _clamp(continue_prob * raise_share, 0.001, 0.80)
            if action == "call":
                return _clamp(continue_prob * (1.0 - raise_share), 0.001, 0.98)
            return _clamp(1.0 - continue_prob, 0.001, 0.98)
        return 0.01

    def _range_action_shares(
        self,
        actions: List[str],
        call_amount: float,
        hero_checked: bool,
        is_raise: bool,
    ) -> Dict[str, float]:
        if not self._range_entries:
            return {a: 1.0 / max(1, len(actions)) for a in actions}
        totals = {a: 0.0 for a in actions}
        for entry in self._range_entries:
            w = entry.get("weight", 0.0)
            for action in actions:
                p = self._combo_action_probability(
                    entry=entry,
                    action=action,
                    call_amount=call_amount,
                    hero_checked=hero_checked,
                    is_raise=is_raise,
                )
                totals[action] += w * p
        return _normalize_distribution(totals)

    def _style_noise_distribution(
        self,
        actions: List[str],
        call_amount: float,
        hero_checked: bool,
        is_raise: bool,
    ) -> Dict[str, float]:
        hand = self.current_hand
        if hand is None:
            return {a: 1.0 / max(1, len(actions)) for a in actions}
        pot = max(1.0, hand.pot_bb)
        hero_image = self._hero_image_score()
        hero_image_adj = hero_image - 0.5
        out = {a: 0.01 for a in actions}

        if hand.street == "preflop":
            if "raise" in out:
                out["raise"] += self.opponent.pfr * 0.95 + self.opponent.three_bet * (0.55 if is_raise else 0.20)
            if "call" in out:
                out["call"] += (
                    max(0.03, self.opponent.vpip - self.opponent.pfr)
                    + self.opponent.limp_rate * 0.35
                    + hero_image_adj * (0.10 + self.opponent.wtsd * 0.16)
                )
            if "fold" in out:
                out["fold"] += max(0.02, 1.0 - self.opponent.vpip) - hero_image_adj * 0.12
            if "check" in out:
                out["check"] += 0.30
            return _normalize_distribution(out)

        if "bet" in out:
            base_cbet = self.opponent.flop_cbet if hand.street == "flop" else self.opponent.turn_cbet if hand.street == "turn" else self.opponent.river_cbet
            out["bet"] += base_cbet * 0.70 + self.opponent.aggression_frequency * 0.25 + (0.10 if hero_checked else 0.0) - hero_image_adj * 0.07
        if "check" in out:
            out["check"] += 0.42 + self.opponent.wtsd * 0.20 + hero_image_adj * 0.06
        if "call" in out:
            pressure = call_amount / max(1.0, pot)
            out["call"] += (
                self.opponent.wtsd * 0.55
                + (self.opponent.vpip - self.opponent.pfr) * 0.62
                - pressure * 0.15
                + hero_image_adj * (0.12 + self.opponent.wtsd * 0.20)
            )
        if "raise" in out:
            out["raise"] += self.opponent.check_raise * 0.80 + max(0.0, self.opponent.af - 2.6) * 0.08
        if "fold" in out:
            pressure = call_amount / max(1.0, pot)
            out["fold"] += 0.34 + pressure * 0.28 - self.opponent.wtsd * 0.20 - hero_image_adj * 0.16
        return _normalize_distribution(out)

    def _villain_action_distribution(
        self,
        actions: List[str],
        call_amount: float,
        hero_checked: bool = False,
        is_raise: bool = False,
    ) -> Dict[str, float]:
        hand = self.current_hand
        if hand is None:
            return {a: 1.0 / max(1, len(actions)) for a in actions}
        actions = [a for a in actions if a]
        if not actions:
            return {}

        combo_entry = self._range_index.get(_canonical_combo(hand.villain_hand))
        if combo_entry is None:
            combo_entry = {
                "cards": _canonical_combo(hand.villain_hand),
                "play_prob": _clamp(self.opponent.vpip, 0.05, 0.95),
                "raise_prob": _clamp(self.opponent.pfr, 0.02, 0.85),
                "call_prob": _clamp(self.opponent.vpip - self.opponent.pfr + 0.12, 0.02, 0.92),
                "threebet_prob": _clamp(self.opponent.three_bet * 2.0, 0.01, 0.75),
                "pre_score": preflop_strength_score(hand.villain_hand[0], hand.villain_hand[1]) / 100.0,
                "strength_q": 0.5,
                "weight": 1.0,
            }

        actual = {}
        for action in actions:
            actual[action] = self._combo_action_probability(
                entry=combo_entry,
                action=action,
                call_amount=call_amount,
                hero_checked=hero_checked,
                is_raise=is_raise,
            )
        actual = _normalize_distribution(actual)
        range_shares = self._range_action_shares(actions, call_amount=call_amount, hero_checked=hero_checked, is_raise=is_raise)
        noise = self._style_noise_distribution(actions, call_amount=call_amount, hero_checked=hero_checked, is_raise=is_raise)

        adherence = self._range_adherence_value
        final = {}
        for action in actions:
            final[action] = adherence * (actual[action] * 0.64 + range_shares[action] * 0.36) + (1.0 - adherence) * noise[action]
        return _normalize_distribution(final)

    def _sample_action(self, distribution: Dict[str, float]) -> str:
        r = self.rng.random()
        cumulative = 0.0
        last = ""
        for action, prob in distribution.items():
            last = action
            cumulative += prob
            if r <= cumulative:
                return action
        return last

    def _update_range_after_action(
        self,
        action: str,
        call_amount: float,
        hero_checked: bool,
        is_raise: bool,
    ) -> None:
        if not self._range_entries:
            return
        adherence = self._range_adherence_value
        for entry in self._range_entries:
            like = self._combo_action_probability(
                entry=entry,
                action=action,
                call_amount=call_amount,
                hero_checked=hero_checked,
                is_raise=is_raise,
            )
            floor = 0.01 + (1.0 - adherence) * 0.10
            entry["weight"] = max(1e-9, entry["weight"] * max(floor, like))

        total = sum(e["weight"] for e in self._range_entries)
        if total > 0:
            for entry in self._range_entries:
                entry["weight"] /= total
        self._refresh_range_summary(event=f"{self.current_hand.street}_{action}" if self.current_hand else action)

    def _refresh_range_summary(self, event: str) -> None:
        hand = self.current_hand
        if hand is None:
            return
        if not self._range_entries:
            hand.villain_range_summary = {}
            return

        sorted_entries = sorted(self._range_entries, key=lambda e: e["weight"], reverse=True)
        top_keys: List[str] = []
        seen = set()
        for e in sorted_entries:
            key = e["key"]
            if key in seen:
                continue
            top_keys.append(key)
            seen.add(key)
            if len(top_keys) >= 12:
                break

        width_threshold = 0.00065
        width_pct = sum(1 for e in self._range_entries if e["weight"] >= width_threshold) / len(self._range_entries)
        value_density = 0.0
        bluff_density = 0.0
        for e in self._range_entries:
            strength = self._combo_postflop_strength(e["cards"], hand.board, hand.street)
            draw = self._combo_draw_strength(e["cards"], hand.board)
            if strength >= 0.74:
                value_density += e["weight"]
            if strength < 0.50 and draw <= 0.18:
                bluff_density += e["weight"]

        actual_key = _combo_key(hand.villain_hand)
        actual_entry = self._range_index.get(_canonical_combo(hand.villain_hand))
        hand.villain_range_summary = {
            "event": event,
            "street": hand.street,
            "adherence": round(self._range_adherence_value, 3),
            "hero_image_score": round(self._hero_image_score(), 3),
            "range_width_pct": round(width_pct, 3),
            "value_density_pct": round(value_density, 3),
            "bluff_density_pct": round(bluff_density, 3),
            "top_weighted_hands": top_keys,
            "actual_villain_hand_key": actual_key,
            "actual_hand_weight": round(actual_entry["weight"], 5) if actual_entry else 0.0,
        }

    def _hero_commit(self, amount: float) -> float:
        hand = self.current_hand
        if hand is None:
            return 0.0
        amt = _round1(min(max(0.0, amount), hand.hero_remaining_bb))
        hand.hero_remaining_bb = _round1(hand.hero_remaining_bb - amt)
        hand.hero_invested_bb = _round1(hand.hero_invested_bb + amt)
        hand.pot_bb = _round1(hand.pot_bb + amt)
        return amt

    def _villain_commit(self, amount: float) -> float:
        hand = self.current_hand
        if hand is None:
            return 0.0
        amt = _round1(min(max(0.0, amount), hand.villain_remaining_bb))
        hand.villain_remaining_bb = _round1(hand.villain_remaining_bb - amt)
        hand.villain_invested_bb = _round1(hand.villain_invested_bb + amt)
        hand.pot_bb = _round1(hand.pot_bb + amt)
        return amt

    def _set_preflop_aggressor(self, who: str) -> None:
        hand = self.current_hand
        if hand is None:
            return
        if hand.street == "preflop":
            hand.preflop_aggressor = who

    def _villain_preflop_first_action(self) -> None:
        hand = self.current_hand
        if hand is None or hand.hand_over:
            return
        to_call_prev = _round1(max(0.0, self.bb - self.sb))
        if hand.villain_remaining_bb <= 0:
            hand.to_call_bb = 0.0
            hand.action_context = "checked_to_hero"
            return

        distribution = self._villain_action_distribution(
            actions=["fold", "call", "raise"],
            call_amount=to_call_prev,
            hero_checked=False,
            is_raise=False,
        )
        selected = self._sample_action(distribution)

        if selected == "fold":
            hand.action_history.append("Villain folds from SB.")
            self._update_range_after_action(action="fold", call_amount=to_call_prev, hero_checked=False, is_raise=False)
            self._end_by_fold(winner="hero", reason="Villain folded preflop.")
            return

        if selected == "raise":
            actual_entry = self._range_index.get(_canonical_combo(hand.villain_hand))
            strength_q = actual_entry["strength_q"] if actual_entry else 0.50
            base = self.rng.uniform(3.1, 5.7) + strength_q * 0.8
            base += max(0.0, self.opponent.af - 2.8) * 0.15
            base -= self.opponent.limp_rate * 0.35
            raise_amount = _round1(_clamp(base, to_call_prev + 1.2, hand.villain_remaining_bb))
            commit = self._villain_commit(raise_amount)
            hand.action_history.append(f"Villain raises {commit:.1f}bb from SB.")
            hand.to_call_bb = _round1(max(0.0, commit - to_call_prev))
            hand.action_context = "facing_bet"
            hand.preflop_aggressor = "villain"
            self._update_range_after_action(action="raise", call_amount=to_call_prev, hero_checked=False, is_raise=False)
        else:
            call_amt = _round1(min(to_call_prev, hand.villain_remaining_bb))
            commit = self._villain_commit(call_amt)
            hand.action_history.append(f"Villain limps/calls {commit:.1f}bb.")
            hand.to_call_bb = 0.0
            hand.action_context = "checked_to_hero"
            self._update_range_after_action(action="call", call_amount=to_call_prev, hero_checked=False, is_raise=False)

    def _villain_postflop_open_action(self) -> None:
        hand = self.current_hand
        if hand is None or hand.hand_over:
            return
        distribution = self._villain_action_distribution(
            actions=["check", "bet"],
            call_amount=0.0,
            hero_checked=False,
            is_raise=False,
        )
        selected = self._sample_action(distribution)
        if hand.villain_remaining_bb <= 0 or selected == "check":
            hand.action_history.append("Villain checks.")
            hand.to_call_bb = 0.0
            hand.action_context = "checked_to_hero"
            hand.hero_phase = "initial"
            self._update_range_after_action(action="check", call_amount=0.0, hero_checked=False, is_raise=False)
            return

        size = self._villain_bet_size()
        commit = self._villain_commit(size)
        hand.action_history.append(f"Villain bets {commit:.1f}bb.")
        hand.to_call_bb = commit
        hand.action_context = "facing_bet"
        hand.hero_phase = "initial"
        self._update_range_after_action(action="bet", call_amount=0.0, hero_checked=False, is_raise=False)

    def _villain_after_hero_check(self) -> None:
        hand = self.current_hand
        if hand is None or hand.hand_over:
            return
        distribution = self._villain_action_distribution(
            actions=["check", "bet"],
            call_amount=0.0,
            hero_checked=True,
            is_raise=False,
        )
        selected = self._sample_action(distribution)
        if hand.villain_remaining_bb <= 0 or selected == "check":
            hand.action_history.append("Villain checks behind.")
            self._update_range_after_action(action="check", call_amount=0.0, hero_checked=True, is_raise=False)
            self._advance_street()
            return

        size = self._villain_bet_size()
        commit = self._villain_commit(size)
        hand.action_history.append(f"Villain bets {commit:.1f}bb after check.")
        hand.to_call_bb = commit
        hand.action_context = "facing_bet"
        hand.hero_phase = "response"
        self._update_range_after_action(action="bet", call_amount=0.0, hero_checked=True, is_raise=False)
        self._update_legal_options()

    def _villain_response_to_hero_aggression(
        self,
        hero_action_amount: float,
        previous_to_call: float,
        is_raise: bool,
    ) -> None:
        hand = self.current_hand
        if hand is None or hand.hand_over:
            return
        call_amount = _round1(max(0.0, hero_action_amount - previous_to_call))
        if call_amount <= 0:
            self._advance_street()
            return

        distribution = self._villain_action_distribution(
            actions=["fold", "call"],
            call_amount=call_amount,
            hero_checked=False,
            is_raise=is_raise,
        )
        selected = self._sample_action(distribution)
        if selected == "fold":
            hand.action_history.append("Villain folds.")
            self._update_range_after_action(action="fold", call_amount=call_amount, hero_checked=False, is_raise=is_raise)
            self._end_by_fold(winner="hero", reason="Villain folded to aggression.")
            return

        commit = self._villain_commit(call_amount)
        hand.action_history.append(f"Villain calls {commit:.1f}bb.")
        self._update_range_after_action(action="call", call_amount=call_amount, hero_checked=False, is_raise=is_raise)
        hand.to_call_bb = 0.0
        if self._is_all_in():
            self._resolve_showdown()
        else:
            self._advance_street()

    def _villain_bet_probability(self, hero_checked: bool) -> float:
        hand = self.current_hand
        if hand is None:
            return 0.3
        street = hand.street
        texture = board_texture_score(hand.board)
        if street == "flop":
            base = self.opponent.flop_cbet if hand.preflop_aggressor == "villain" else 0.20 + self.opponent.aggression_frequency * 0.40
        elif street == "turn":
            base = self.opponent.turn_cbet if hand.preflop_aggressor == "villain" else 0.16 + self.opponent.aggression_frequency * 0.34
        elif street == "river":
            base = self.opponent.river_cbet if hand.preflop_aggressor == "villain" else 0.12 + self.opponent.aggression_frequency * 0.28
        else:
            base = 0.26 + self.opponent.pfr * 0.25

        if hero_checked:
            base += 0.12
        base += max(0.0, self.opponent.af - 2.0) * 0.04
        base -= texture * 0.03 if street in {"turn", "river"} else 0.0
        return _clamp(base, 0.05, 0.92)

    def _villain_bet_size(self) -> float:
        hand = self.current_hand
        if hand is None:
            return 2.0
        pot = max(1.0, hand.pot_bb)
        texture = board_texture_score(hand.board)
        entry = self._range_index.get(_canonical_combo(hand.villain_hand))
        combo_strength = self._combo_postflop_strength(
            _canonical_combo(hand.villain_hand),
            hand.board,
            hand.street,
        )
        if hand.street == "preflop":
            combo_strength = entry["strength_q"] if entry else combo_strength

        if self.opponent.af < 1.2:
            size_ratio = self.rng.uniform(0.38, 0.78)
        elif self.opponent.af > 3.2:
            size_ratio = self.rng.uniform(0.42, 1.20)
        else:
            size_ratio = self.rng.uniform(0.34, 0.98)

        size_ratio += max(0.0, combo_strength - 0.52) * 0.28
        size_ratio += 0.10 if texture > 1.4 else 0.0
        if self.opponent.style_label.lower().find("calling station") >= 0:
            size_ratio += 0.05
        raw = pot * _clamp(size_ratio, 0.25, 1.35)
        return _round1(_clamp(raw, 1.0, hand.villain_remaining_bb))

    def _villain_strength(self) -> float:
        hand = self.current_hand
        if hand is None:
            return 0.4
        if hand.street == "preflop":
            return _clamp(preflop_strength_score(hand.villain_hand[0], hand.villain_hand[1]) / 100.0, 0.0, 1.0)

        board = hand.board
        rank = best_hand_rank(hand.villain_hand + board)
        category = rank[0] / 8.0
        kicker = 0.0
        if rank[1]:
            kicker = rank[1][0] / 14.0
        draw_bonus = 0.0
        if len(board) < 5:
            texture = board_texture_score(board)
            broadway_cards = sum(1 for c in hand.villain_hand if c[0] in "TJQKA")
            draw_bonus = broadway_cards * 0.04 + texture * 0.03
        return _clamp(category * 0.78 + kicker * 0.14 + draw_bonus, 0.0, 1.2)

    def _villain_fold_probability(self, call_amount: float, is_raise: bool) -> float:
        hand = self.current_hand
        if hand is None:
            return 0.5
        pot = max(1.0, hand.pot_bb)
        pot_odds = call_amount / (pot + call_amount)
        strength = self._villain_strength()
        vpip_pfr_gap = max(0.0, self.opponent.vpip - self.opponent.pfr)
        sticky = _clamp(
            0.22 + self.opponent.wtsd * 0.45 + vpip_pfr_gap * 0.68 - self.opponent.af * 0.05,
            0.05,
            0.96,
        )
        pressure = call_amount / pot
        fold = 0.48 + pressure * 0.24 + pot_odds * 0.25 - strength * 0.52 - sticky * 0.34
        if is_raise and hand.street == "preflop":
            fold += self.opponent.fold_to_3bet * 0.42
        if self.opponent.style_label.lower().find("calling") >= 0:
            fold -= 0.10
        return _clamp(fold, 0.02, 0.92)

    def _is_all_in(self) -> bool:
        hand = self.current_hand
        if hand is None:
            return False
        return hand.hero_remaining_bb <= 0.01 or hand.villain_remaining_bb <= 0.01

    def _advance_street(self) -> None:
        hand = self.current_hand
        if hand is None or hand.hand_over:
            return
        nxt = _next_street(hand.street)
        if nxt is None:
            self._resolve_showdown()
            return

        hand.street = nxt
        hand.board = hand.full_board[: _street_board_count(nxt)]
        hand.to_call_bb = 0.0
        hand.action_context = "checked_to_hero"
        hand.hero_phase = "initial"
        hand.hero_first_this_street = self._hero_first_on_street(nxt, hand.button_on_hero)
        hand.action_history.append(f"--- {nxt.upper()} ---")
        self._refresh_range_summary(event=f"enter_{nxt}")

        if hand.hero_first_this_street:
            self._update_legal_options()
            return

        self._villain_postflop_open_action()
        if not hand.hand_over:
            self._update_legal_options()

    def _resolve_showdown(self) -> None:
        hand = self.current_hand
        if hand is None or hand.hand_over:
            return
        hand.board = hand.full_board[:5]
        self._refresh_range_summary(event="showdown")
        hero_rank = best_hand_rank(hand.hero_hand + hand.board)
        villain_rank = best_hand_rank(hand.villain_hand + hand.board)

        if hero_rank > villain_rank:
            hero_share = 1.0
            winner = "hero"
        elif villain_rank > hero_rank:
            hero_share = 0.0
            winner = "villain"
        else:
            hero_share = 0.5
            winner = "split"

        hero_win = hand.pot_bb * hero_share
        hero_delta = hero_win - hand.hero_invested_bb
        hand.hero_delta_bb = round(hero_delta, 3)
        self.hero_net_bb = round(self.hero_net_bb + hand.hero_delta_bb, 3)
        hand.hand_over = True
        hand.legal_actions = []
        hand.size_options_bb = []
        hand.to_call_bb = 0.0
        hand.action_context = "showdown"
        hand.showdown = {
            "winner": winner,
            "hero_hand_category": rank_category_name(hero_rank),
            "villain_hand_category": rank_category_name(villain_rank),
            "hero_share": round(hero_share, 3),
            "hero_delta_bb": round(hero_delta, 3),
            "board": list(hand.board),
        }
        hand.action_history.append(f"Showdown: {winner}. Hero delta {hero_delta:.2f}bb.")

    def _end_by_fold(self, winner: str, reason: str) -> None:
        hand = self.current_hand
        if hand is None or hand.hand_over:
            return
        if winner == "hero":
            hero_win = hand.pot_bb
        else:
            hero_win = 0.0
        hero_delta = hero_win - hand.hero_invested_bb
        hand.hero_delta_bb = round(hero_delta, 3)
        self.hero_net_bb = round(self.hero_net_bb + hand.hero_delta_bb, 3)
        hand.hand_over = True
        hand.legal_actions = []
        hand.size_options_bb = []
        hand.to_call_bb = 0.0
        hand.action_context = "hand_over"
        hand.showdown = {
            "winner": winner,
            "reason": reason,
            "hero_delta_bb": round(hero_delta, 3),
            "board": list(hand.board),
        }
        hand.action_history.append(f"Hand ends: {reason}")

    def _update_legal_options(self) -> None:
        hand = self.current_hand
        if hand is None or hand.hand_over:
            return
        effective_stack = max(0.0, min(hand.hero_remaining_bb, hand.villain_remaining_bb))
        to_call = max(0.0, hand.to_call_bb)

        if to_call > 0:
            legal = ["fold", "call"]
            size_opts = self._raise_size_options(to_call=to_call, effective=effective_stack, pot=hand.pot_bb)
            if size_opts:
                legal.append("raise")
            hand.legal_actions = legal
            hand.size_options_bb = size_opts
            hand.action_context = "facing_bet"
        else:
            legal = ["check"]
            size_opts = self._bet_size_options(effective=effective_stack, pot=hand.pot_bb)
            if size_opts:
                legal.append("bet")
            hand.legal_actions = legal
            hand.size_options_bb = size_opts
            hand.action_context = "checked_to_hero"

    def _bet_size_options(self, effective: float, pot: float) -> List[float]:
        if effective <= 0.05:
            return []
        base = [pot * p for p in BET_SIZE_PCTS] + [pot]
        options = sorted({_round1(_clamp(v, 1.0, effective)) for v in base if v > 0})
        if effective >= 1.0:
            options.append(_round1(effective))
        options = sorted(set(v for v in options if 0.8 <= v <= effective + 1e-9))
        return options[:6]

    def _raise_size_options(self, to_call: float, effective: float, pot: float) -> List[float]:
        if effective <= to_call + 0.05:
            return []
        min_raise = max(to_call * 2.0, to_call + 1.0)
        base = [min_raise, to_call + pot * 0.5, to_call + pot * 0.75, to_call + pot * 1.25, effective]
        options = sorted({_round1(_clamp(v, min_raise, effective)) for v in base if v > to_call})
        options = [v for v in options if v > to_call + 0.1 and v <= effective + 1e-9]
        return options[:6]
