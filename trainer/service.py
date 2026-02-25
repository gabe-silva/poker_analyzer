"""Application service layer for the poker trainer."""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any, Dict, List

from trainer.archetypes import archetype_options
from trainer.constants import (
    ACTION_CONTEXTS,
    DEFAULT_BB,
    DEFAULT_SB,
    DEFAULT_STACK_BB,
    NODE_TYPES,
    POSITION_SETS,
    STREETS,
)
from trainer.ev_engine import evaluate_decision
from trainer.live_play import LiveMatch
from trainer.scenario import generate_scenario
from trainer.storage import TrainerStore


class TrainerService:
    """High-level API used by HTTP handlers and scripts."""

    def __init__(self, db_path: Path):
        self.store = TrainerStore(db_path=db_path)
        self.live_sessions: Dict[str, LiveMatch] = {}
        self._profile_cache: Dict[str, Dict[str, Any]] = {}
        self._root_dir = Path(__file__).resolve().parent.parent

    @staticmethod
    def _charlie_preset() -> dict:
        """Profile provided by the user from analyzer dashboard."""
        return {
            "key": "charlie",
            "name": "CHARLIE",
            "source": "preset",
            "style_label": "Loose-Passive (Calling Station)",
            "hands_analyzed": 176,
            "vpip": 0.574,
            "pfr": 0.199,
            "three_bet": 0.077,
            "fold_to_3bet": 0.0,
            "limp_rate": 0.386,
            "af": 0.83,
            "aggression_frequency": 0.298,
            "flop_cbet": 0.75,
            "turn_cbet": 0.0,
            "river_cbet": 0.0,
            "double_barrel": 0.579,
            "triple_barrel": 0.667,
            "check_raise": 0.105,
            "wtsd": 0.619,
            "w_sd": 0.734,
            "tendencies": [
                "Plays very loose preflop (VPIP > 33%)",
                "Large VPIP-PFR gap (calls too much)",
                "Limps frequently",
                "C-bets flops frequently then gives up on later streets",
                "Passive postflop without clear value",
            ],
            "exploits": [
                {
                    "category": "preflop",
                    "description": "Raises and limps too wide.",
                    "counter_strategy": "Isolate bigger preflop and value bet wider.",
                },
                {
                    "category": "postflop",
                    "description": "High flop c-bet, weak turn follow-through.",
                    "counter_strategy": "Float wider in position and pressure turns.",
                },
            ],
        }

    @staticmethod
    def _baseline_reg_preset() -> dict:
        return {
            "key": "tag_reg",
            "name": "TAG REG",
            "source": "preset",
            "style_label": "TAG Regular",
            "hands_analyzed": 0,
            "vpip": 0.23,
            "pfr": 0.19,
            "three_bet": 0.085,
            "fold_to_3bet": 0.52,
            "limp_rate": 0.05,
            "af": 2.5,
            "aggression_frequency": 0.42,
            "flop_cbet": 0.60,
            "turn_cbet": 0.47,
            "river_cbet": 0.35,
            "check_raise": 0.11,
            "wtsd": 0.28,
            "w_sd": 0.52,
            "tendencies": [],
            "exploits": [],
        }

    def _preset_profiles(self) -> List[dict]:
        return [self._charlie_preset(), self._baseline_reg_preset()]

    def _load_player_mappings(self) -> Dict[str, str]:
        csv_path = self._root_dir / "names.csv"
        if not csv_path.exists():
            return {}
        with open(csv_path, "r", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        if len(rows) < 2:
            return {}
        out: Dict[str, str] = {}
        for name, player_id in zip(rows[0], rows[1]):
            if name and player_id:
                out[name.strip().lower()] = player_id.strip()
        return out

    def analyzer_players(self) -> List[str]:
        return sorted(self._load_player_mappings().keys())

    def _hands_snapshot_signature(self) -> str:
        """Stable signature of analyzer hand files used for cache invalidation."""
        hands_dir = self._root_dir / "hands"
        if not hands_dir.exists():
            return "missing"
        parts: List[str] = []
        for hand_file in sorted(hands_dir.glob("*.json")):
            try:
                st = hand_file.stat()
            except OSError:
                continue
            parts.append(f"{hand_file.name}:{st.st_size}:{st.st_mtime_ns}")
        return "|".join(parts)

    def analyzer_profile(self, player_name: str) -> dict:
        key = str(player_name or "").strip().lower()
        if not key:
            raise ValueError("player_name is required")
        hands_snapshot = self._hands_snapshot_signature()
        cached = self._profile_cache.get(key)
        if cached and cached.get("snapshot") == hands_snapshot:
            profile = cached.get("profile")
            if isinstance(profile, dict):
                return profile

        mappings = self._load_player_mappings()
        player_id = mappings.get(key)
        if not player_id:
            raise ValueError(f"Player not found in names.csv: {player_name}")

        hands_dir = self._root_dir / "hands"
        if not hands_dir.exists():
            raise ValueError(f"Hands directory not found: {hands_dir}")

        from parser import load_hands  # local import to avoid startup cost
        from stats.aggregate import generate_profile

        all_hands = []
        for hand_file in sorted(hands_dir.glob("*.json")):
            all_hands.extend(load_hands(hand_file))
        if not all_hands:
            raise ValueError("No hands loaded from hands directory")

        profile = generate_profile(all_hands, player_id)
        af = profile.postflop.total_aggression_factor
        if af == float("inf") or math.isinf(af):
            af = 6.0
        built = {
            "key": key,
            "name": key.upper(),
            "source": "analyzer",
            "style_label": profile.play_style.value,
            "hands_analyzed": profile.hands_analyzed,
            "vpip": round(profile.preflop.vpip, 4),
            "pfr": round(profile.preflop.pfr, 4),
            "three_bet": round(profile.preflop.three_bet_frequency, 4),
            "fold_to_3bet": round(profile.preflop.fold_to_3bet, 4),
            "limp_rate": round(profile.preflop.limp_rate, 4),
            "af": round(float(af), 3),
            "aggression_frequency": round(profile.postflop.total_aggression_frequency, 4),
            "flop_cbet": round(profile.postflop.flop.cbet_frequency, 4),
            "turn_cbet": round(profile.postflop.turn.cbet_frequency, 4),
            "river_cbet": round(profile.postflop.river.cbet_frequency, 4),
            "double_barrel": round(profile.postflop.double_barrel_frequency, 4),
            "triple_barrel": round(profile.postflop.triple_barrel_frequency, 4),
            "check_raise": round(profile.postflop.check_raise_frequency, 4),
            "wtsd": round(profile.showdown.wtsd, 4),
            "w_sd": round(profile.showdown.w_sd, 4),
            "tendencies": list(profile.tendencies[:8]),
            "exploits": [
                {
                    "category": e.category,
                    "description": e.description,
                    "counter_strategy": e.counter_strategy,
                }
                for e in profile.exploits[:5]
            ],
        }
        self._profile_cache[key] = {
            "snapshot": hands_snapshot,
            "profile": built,
        }
        return built

    def app_config(self) -> Dict[str, Any]:
        return {
            "streets": STREETS,
            "node_types": NODE_TYPES,
            "action_contexts": ACTION_CONTEXTS,
            "position_sets": POSITION_SETS,
            "archetypes": archetype_options(),
            "live": {
                "presets": self._preset_profiles(),
                "analyzer_players": self.analyzer_players(),
                "defaults": {
                    "opponent_source": "preset",
                    "preset_key": "charlie",
                    "starting_stack_bb": DEFAULT_STACK_BB,
                    "targeted_mode": False,
                    "target_config": {
                        "street": "flop",
                        "node_type": "single_raised_pot",
                        "action_context": "facing_bet",
                        "hero_position": "BTN",
                    },
                },
            },
            "defaults": {
                "num_players": 6,
                "street": "flop",
                "node_type": "single_raised_pot",
                "action_context": "facing_bet_and_call",
                "hero_position": "BTN",
                "players_in_hand": 3,
                "equal_stacks": True,
                "default_stack_bb": DEFAULT_STACK_BB,
                "sb": DEFAULT_SB,
                "bb": DEFAULT_BB,
                "hero_profile": {
                    "vpip": 0.30,
                    "pfr": 0.22,
                    "af": 2.8,
                    "three_bet": 0.09,
                    "fold_to_3bet": 0.54,
                },
                "randomize_hero_profile": False,
                "randomize_archetypes": False,
            },
        }

    def generate(self, payload: dict) -> dict:
        scenario = generate_scenario(payload)
        self.store.save_scenario(scenario)
        return scenario

    def get_scenario(self, scenario_id: str) -> dict:
        scenario = self.store.get_scenario(scenario_id)
        if scenario is None:
            raise ValueError(f"Scenario not found: {scenario_id}")
        return scenario

    def evaluate(self, payload: dict) -> dict:
        scenario_id = payload.get("scenario_id")
        if not scenario_id:
            raise ValueError("scenario_id is required")
        decision = payload.get("decision")
        if not isinstance(decision, dict):
            raise ValueError("decision is required")

        free_response = str(payload.get("free_response", "")).strip()
        simulations = int(payload.get("simulations", 260))

        scenario = self.store.get_scenario(scenario_id)
        if scenario is None:
            raise ValueError(f"Scenario not found: {scenario_id}")

        evaluation = evaluate_decision(scenario, decision, simulations=simulations)
        attempt_id = self.store.save_attempt(
            scenario=scenario,
            decision=decision,
            evaluation=evaluation,
            free_response=free_response,
        )

        return {
            "attempt_id": attempt_id,
            "scenario": scenario,
            "evaluation": evaluation,
        }

    def progress(self) -> dict:
        return self.store.progress_summary()

    def clear_saved_hands(self) -> dict:
        return self.store.clear_saved_hands()

    def live_start(self, payload: dict) -> dict:
        source = str(payload.get("opponent_source", "preset"))
        opponent_profile: dict
        if source == "analyzer":
            name = str(payload.get("analyzer_player", "")).strip()
            if not name:
                raise ValueError("analyzer_player is required for analyzer source")
            opponent_profile = self.analyzer_profile(name)
        elif source == "custom":
            raw = payload.get("opponent_profile")
            if not isinstance(raw, dict):
                raise ValueError("opponent_profile is required for custom source")
            opponent_profile = dict(raw)
            opponent_profile.setdefault("name", "CUSTOM OPPONENT")
            opponent_profile.setdefault("source", "custom")
        else:
            preset_key = str(payload.get("preset_key", "charlie")).lower()
            preset_map = {p["key"]: p for p in self._preset_profiles()}
            opponent_profile = dict(preset_map.get(preset_key) or self._charlie_preset())

        targeted_mode = bool(payload.get("targeted_mode", False))
        target_config = payload.get("target_config") if isinstance(payload.get("target_config"), dict) else None
        match = LiveMatch(
            opponent_profile=opponent_profile,
            seed=payload.get("seed"),
            starting_stack_bb=float(payload.get("starting_stack_bb", DEFAULT_STACK_BB)),
            sb=DEFAULT_SB,
            bb=DEFAULT_BB,
            mode="targeted" if targeted_mode else "full_game",
            target_config=target_config,
        )
        self.live_sessions[match.session_id] = match
        return match.state()

    def live_state(self, session_id: str) -> dict:
        session = self.live_sessions.get(session_id)
        if session is None:
            raise ValueError(f"Live session not found: {session_id}")
        return session.state()

    def live_action(self, payload: dict) -> dict:
        session_id = str(payload.get("session_id", "")).strip()
        if not session_id:
            raise ValueError("session_id is required")
        session = self.live_sessions.get(session_id)
        if session is None:
            raise ValueError(f"Live session not found: {session_id}")
        return session.hero_action(
            action=str(payload.get("action", "")),
            size_bb=payload.get("size_bb"),
            intent=payload.get("intent"),
        )

    def live_new_hand(self, payload: dict) -> dict:
        session_id = str(payload.get("session_id", "")).strip()
        if not session_id:
            raise ValueError("session_id is required")
        session = self.live_sessions.get(session_id)
        if session is None:
            raise ValueError(f"Live session not found: {session_id}")
        return session.start_next_hand()
