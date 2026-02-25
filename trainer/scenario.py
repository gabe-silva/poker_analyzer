"""Scenario schema and generation logic for trainer drills."""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from trainer.archetypes import ARCHETYPES, archetype_by_key
from trainer.cards import full_deck
from trainer.constants import (
    ACTION_CONTEXTS,
    BET_SIZE_PCTS,
    DEFAULT_BB,
    DEFAULT_SB,
    DEFAULT_STACK_BB,
    NODE_TYPES,
    STREETS,
    positions_for_table,
)
from trainer.hero_profile import parse_hero_profile, randomize_hero_profile


@dataclass
class SeatState:
    """One seat state in a generated scenario."""

    seat: int
    position: str
    is_hero: bool
    archetype_key: str
    archetype_label: str
    stack_bb: float
    in_hand: bool
    role: str

    def to_dict(self) -> dict:
        return {
            "seat": self.seat,
            "position": self.position,
            "is_hero": self.is_hero,
            "archetype_key": self.archetype_key,
            "archetype_label": self.archetype_label,
            "stack_bb": round(self.stack_bb, 2),
            "in_hand": self.in_hand,
            "role": self.role,
        }


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _street_board_count(street: str) -> int:
    return {"preflop": 0, "flop": 3, "turn": 4, "river": 5}[street]


def _node_preflop_pot(node_type: str) -> float:
    if node_type == "single_raised_pot":
        return 6.5
    if node_type == "three_bet_pot":
        return 18.0
    return 33.0


def _pot_for_spot(node_type: str, street: str, players_in_hand: int, rng: random.Random) -> float:
    base = _node_preflop_pot(node_type)
    if street == "preflop":
        return base

    pot = base
    if street in {"flop", "turn", "river"}:
        pot *= rng.uniform(1.1, 1.45)
    if street in {"turn", "river"}:
        pot *= rng.uniform(1.2, 1.6)
    if street == "river":
        pot *= rng.uniform(1.15, 1.55)
    pot *= 1.0 + max(0, players_in_hand - 2) * 0.16
    return round(max(5.0, pot), 2)


def _default_archetype_for_position(position: str, rng: random.Random) -> str:
    """Weighted default so generated pools look realistic."""
    if position in {"SB", "BB"}:
        pool = ["calling_station", "weak_tight", "tag_reg", "overcaller_preflop", "lag_reg"]
    elif position in {"UTG", "LJ"}:
        pool = ["tag_reg", "nit", "weak_tight", "trappy"]
    else:
        pool = ["tag_reg", "lag_reg", "one_and_done", "fit_or_fold", "calling_station"]
    return rng.choice(pool)


def _preflop_order(positions: List[str]) -> List[str]:
    """Canonical preflop action order for ring/cash labels used in this app."""
    canonical = ["UTG", "LJ", "HJ", "CO", "BTN", "SB", "BB"]
    ordered = [p for p in canonical if p in positions]
    for p in positions:
        if p not in ordered:
            ordered.append(p)
    return ordered


def _postflop_order(positions: List[str]) -> List[str]:
    """Postflop starts left of button (SB first if present, else BB in HU)."""
    if "SB" in positions:
        start = positions.index("SB")
        return positions[start:] + positions[:start]
    if len(positions) == 2 and "BB" in positions and "BTN" in positions:
        return ["BB", "BTN"]
    if "BB" in positions:
        start = positions.index("BB")
        return positions[start:] + positions[:start]
    return positions


def _active_acting_order(
    table_positions: List[str],
    active_positions: List[str],
    street: str,
) -> List[str]:
    if street == "preflop":
        base = _preflop_order(table_positions)
    else:
        base = _postflop_order(table_positions)
    return [p for p in base if p in active_positions]


def _ordered_roles_for_hero_to_act(
    requested_context: str,
    active_order: List[str],
    hero_position: str,
) -> tuple[Dict[str, str], str]:
    """
    Assign bettor/caller in legal order so hero acts next.

    Returns:
        (roles, resolved_action_context)
    """
    roles = {p: "waiting" for p in active_order}
    roles[hero_position] = "hero_to_act"

    if hero_position not in active_order:
        return roles, "checked_to_hero"

    hero_idx = active_order.index(hero_position)
    prefix = active_order[:hero_idx]  # players who act before hero

    if requested_context == "facing_bet_and_call":
        if len(prefix) >= 2:
            bettor = prefix[-2]
            caller = prefix[-1]
            roles[bettor] = "bettor"
            roles[caller] = "caller"
            return roles, "facing_bet_and_call"
        if len(prefix) >= 1:
            bettor = prefix[-1]
            roles[bettor] = "bettor"
            return roles, "facing_bet"
        return roles, "checked_to_hero"

    if requested_context == "facing_bet":
        if len(prefix) >= 1:
            bettor = prefix[-1]
            roles[bettor] = "bettor"
            return roles, "facing_bet"
        return roles, "checked_to_hero"

    return roles, "checked_to_hero"


def _apply_in_hand_target(
    seats: List[SeatState],
    players_in_hand: int,
    hero_position: str,
    rng: random.Random,
) -> None:
    players_in_hand = max(2, min(players_in_hand, len(seats)))
    hero_idx = next(i for i, seat in enumerate(seats) if seat.position == hero_position)
    seats[hero_idx].in_hand = True

    currently = [s for s in seats if s.in_hand]
    if len(currently) > players_in_hand:
        removable = [s for s in currently if not s.is_hero]
        rng.shuffle(removable)
        for seat in removable[: len(currently) - players_in_hand]:
            seat.in_hand = False
    elif len(currently) < players_in_hand:
        available = [s for s in seats if not s.in_hand and not s.is_hero]
        rng.shuffle(available)
        for seat in available[: players_in_hand - len(currently)]:
            seat.in_hand = True


def _build_action_history(
    street: str,
    node_type: str,
    roles: Dict[str, str],
    active_order: List[str],
    resolved_context: str,
    to_call_bb: float,
    pot_bb: float,
    hero_position: str,
) -> List[str]:
    node_text = {
        "single_raised_pot": "single-raised pot",
        "three_bet_pot": "3-bet pot",
        "four_bet_pot": "4-bet pot",
    }[node_type]
    history = [
        f"Preflop setup: {node_text}.",
    ]
    if hero_position not in active_order:
        history.append(f"Hero ({hero_position}) now faces decision.")
        return history

    hero_idx = active_order.index(hero_position)
    prefix = active_order[:hero_idx]

    if street == "preflop" and not prefix:
        history.append(f"Hero ({hero_position}) now faces preflop decision.")
        return history

    if resolved_context == "facing_bet_and_call" and len(prefix) >= 2:
        for pos in prefix[:-2]:
            history.append(f"{pos} checks.")
        history.append(f"{prefix[-2]} bets {to_call_bb:.1f}bb into {pot_bb:.1f}bb.")
        history.append(f"{prefix[-1]} calls {to_call_bb:.1f}bb.")
    elif resolved_context == "facing_bet" and len(prefix) >= 1:
        for pos in prefix[:-1]:
            history.append(f"{pos} checks.")
        history.append(f"{prefix[-1]} bets {to_call_bb:.1f}bb into {pot_bb:.1f}bb.")
    else:
        if prefix:
            for pos in prefix:
                history.append(f"{pos} checks.")
        history.append("Action checks to Hero.")
    return history


def _round_options(options: List[float], min_value: float, max_value: float) -> List[float]:
    out = sorted(
        {
            round(_clamp(v, min_value, max_value), 1)
            for v in options
            if max_value > 0
        }
    )
    return [v for v in out if v >= min_value and v <= max_value]


def generate_scenario(payload: dict) -> dict:
    """Generate a scenario from user filter/config payload."""
    seed = int(payload.get("seed", random.randint(1, 10_000_000)))
    rng = random.Random(seed)

    num_players = int(payload.get("num_players", 6))
    if num_players < 2 or num_players > 7:
        raise ValueError("num_players must be between 2 and 7")

    street = payload.get("street", "flop")
    if street not in STREETS:
        raise ValueError(f"street must be one of {STREETS}")

    node_type = payload.get("node_type", "single_raised_pot")
    if node_type not in NODE_TYPES:
        raise ValueError(f"node_type must be one of {NODE_TYPES}")

    action_context = payload.get("action_context", "facing_bet")
    if action_context not in ACTION_CONTEXTS:
        raise ValueError(f"action_context must be one of {ACTION_CONTEXTS}")

    positions = positions_for_table(num_players)
    hero_position = payload.get("hero_position", "BTN")
    if hero_position not in positions:
        hero_position = positions[0]

    equal_stacks = bool(payload.get("equal_stacks", True))
    default_stack_bb = float(payload.get("default_stack_bb", DEFAULT_STACK_BB))
    default_stack_bb = _clamp(default_stack_bb, 20.0, 400.0)

    sb = float(payload.get("sb", DEFAULT_SB))
    bb = float(payload.get("bb", DEFAULT_BB))
    if sb <= 0 or bb <= 0 or sb >= bb:
        sb, bb = DEFAULT_SB, DEFAULT_BB

    randomize_hero = bool(payload.get("randomize_hero_profile", False))
    randomize_archetypes = bool(payload.get("randomize_archetypes", False))
    hero_profile = (
        randomize_hero_profile(rng)
        if randomize_hero
        else parse_hero_profile(payload.get("hero_profile"))
    )

    seat_inputs = payload.get("seats", [])
    seat_overrides: Dict[str, dict] = {
        str(s.get("position")): s for s in seat_inputs if "position" in s
    }

    seats: List[SeatState] = []
    for idx, position in enumerate(positions):
        is_hero = position == hero_position
        override = seat_overrides.get(position, {})
        archetype_key = "hero"
        archetype_label = "Hero"
        if not is_hero:
            if randomize_archetypes:
                archetype_key = _default_archetype_for_position(position, rng)
            else:
                archetype_key = override.get("archetype_key") or _default_archetype_for_position(position, rng)
                if archetype_key not in ARCHETYPES:
                    archetype_key = "tag_reg"
            archetype_label = archetype_by_key(archetype_key).label

        stack_bb = float(override.get("stack_bb", default_stack_bb))
        if equal_stacks:
            stack_bb = default_stack_bb
        stack_bb = _clamp(stack_bb, 10.0, 500.0)

        in_hand = bool(override.get("in_hand", True))
        if is_hero:
            in_hand = True

        seats.append(
            SeatState(
                seat=idx + 1,
                position=position,
                is_hero=is_hero,
                archetype_key=archetype_key,
                archetype_label=archetype_label,
                stack_bb=stack_bb,
                in_hand=in_hand,
                role="out",
            )
        )

    players_in_hand = int(payload.get("players_in_hand", min(num_players, 3)))
    _apply_in_hand_target(seats, players_in_hand, hero_position, rng)

    active_positions = [s.position for s in seats if s.in_hand]
    active_order = _active_acting_order(positions, active_positions, street)
    roles, resolved_action_context = _ordered_roles_for_hero_to_act(
        requested_context=action_context,
        active_order=active_order,
        hero_position=hero_position,
    )
    for seat in seats:
        if seat.in_hand:
            seat.role = roles.get(seat.position, "waiting")

    pot_bb = _pot_for_spot(node_type, street, len(active_positions), rng)

    to_call_bb = 0.0
    if resolved_action_context == "facing_bet":
        to_call_bb = round(pot_bb * rng.uniform(0.22, 0.62), 1)
    elif resolved_action_context == "facing_bet_and_call":
        to_call_bb = round(pot_bb * rng.uniform(0.16, 0.45), 1)

    hero_stack = next(s.stack_bb for s in seats if s.is_hero)
    effective_stack = min(
        [hero_stack] + [s.stack_bb for s in seats if s.in_hand and not s.is_hero]
    )

    deck = full_deck()
    hero_hand = rng.sample(deck, 2)
    for c in hero_hand:
        deck.remove(c)
    board = []
    board_count = _street_board_count(street)
    if board_count > 0:
        board = rng.sample(deck, board_count)
        for c in board:
            deck.remove(c)

    if to_call_bb > 0:
        legal_actions = ["fold", "call", "raise"]
        raise_options = _round_options(
            [to_call_bb + pot_bb * p for p in BET_SIZE_PCTS] + [to_call_bb * 2.0],
            min_value=max(to_call_bb * 2.0, to_call_bb + 1.0),
            max_value=max(2.0, effective_stack),
        )
        if not raise_options:
            raise_options = [round(max(2.0, min(effective_stack, to_call_bb * 2.0)), 1)]
        bet_options: List[float] = []
    else:
        legal_actions = ["check", "bet"]
        bet_options = _round_options(
            [pot_bb * p for p in BET_SIZE_PCTS],
            min_value=1.0,
            max_value=max(2.0, effective_stack),
        )
        if not bet_options:
            bet_options = [round(max(1.0, effective_stack * 0.3), 1)]
        raise_options = []

    history = _build_action_history(
        street=street,
        node_type=node_type,
        roles=roles,
        active_order=active_order,
        resolved_context=resolved_action_context,
        to_call_bb=to_call_bb,
        pot_bb=pot_bb,
        hero_position=hero_position,
    )

    scenario_id = f"scn_{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    position_guidance = hero_profile.position_guidance(hero_position, street)

    return {
        "scenario_id": scenario_id,
        "created_at": now_iso,
        "seed": seed,
        "num_players": num_players,
        "players_in_hand": len(active_positions),
        "street": street,
        "node_type": node_type,
        "action_context": resolved_action_context,
        "action_context_requested": action_context,
        "action_context_resolved": resolved_action_context,
        "blinds": {"sb": sb, "bb": bb},
        "hero_position": hero_position,
        "hero_hand": hero_hand,
        "board": board,
        "pot_bb": round(pot_bb, 2),
        "to_call_bb": round(to_call_bb, 2),
        "effective_stack_bb": round(effective_stack, 2),
        "legal_actions": legal_actions,
        "bet_size_options_bb": bet_options,
        "raise_size_options_bb": raise_options,
        "action_history": history,
        "seats": [s.to_dict() for s in seats],
        "hero_profile": hero_profile.to_dict(),
        "position_guidance": position_guidance,
        "randomization": {
            "hero_profile": randomize_hero,
            "archetypes": randomize_archetypes,
        },
        "decision_prompt": (
            f"Hero ({hero_position}) to act on {street}. "
            "Choose one move and explain your exploit logic."
        ),
    }
