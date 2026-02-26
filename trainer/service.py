"""Application service layer for the poker trainer."""

from __future__ import annotations

from collections import Counter
import json
import math
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set, Tuple

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

    MAX_UPLOAD_FILE_BYTES = 15 * 1024 * 1024
    MAX_UPLOAD_BATCH_BYTES = 100 * 1024 * 1024

    def __init__(self, db_path: Path):
        self.store = TrainerStore(db_path=db_path)
        self.live_sessions: Dict[str, LiveMatch] = {}
        self._profile_cache: Dict[str, Dict[str, Any]] = {}
        self._root_dir = Path(__file__).resolve().parent.parent
        self._uploaded_hands_dir = self._root_dir / "trainer" / "data" / "uploaded_hands"
        self._uploaded_hands_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sanitize_upload_filename(filename: str, fallback_index: int) -> str:
        raw = Path(str(filename or "")).name
        if not raw:
            raw = f"upload_{fallback_index}.json"
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", raw)
        if not safe.lower().endswith(".json"):
            safe = f"{safe}.json"
        return safe

    @staticmethod
    def _parse_names_input(player_name: Any) -> List[str]:
        if isinstance(player_name, list):
            tokens = [str(v).strip() for v in player_name]
        else:
            text = str(player_name or "").strip()
            if not text:
                return []
            tokens = [part.strip() for part in re.split(r"[,\n;]+", text)]
        return [token for token in tokens if token]

    def _uploaded_hand_files(self) -> List[Path]:
        if not self._uploaded_hands_dir.exists():
            return []
        return sorted(self._uploaded_hands_dir.glob("*.json"))

    def _uploaded_player_index(self) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Set[str]], int]:
        """
        Build player buckets keyed by player id plus an alias lookup.

        Returns:
            (by_player_id, alias_to_player_id_keys, total_hands)
        """
        by_player_id: Dict[str, Dict[str, Any]] = {}
        alias_to_ids: Dict[str, Set[str]] = {}
        total_hands = 0
        for file_path in self._uploaded_hand_files():
            try:
                raw = json.loads(file_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            hands = raw.get("hands", raw if isinstance(raw, list) else [])
            if not isinstance(hands, list):
                continue
            total_hands += len(hands)
            for hand in hands:
                if not isinstance(hand, dict):
                    continue
                seen_ids_in_hand: Set[str] = set()
                for player in hand.get("players", []) or []:
                    if not isinstance(player, dict):
                        continue
                    player_id = str(player.get("id", "")).strip()
                    username = str(player.get("name", "")).strip() or player_id
                    if not player_id or not username:
                        continue
                    id_key = player_id.lower()
                    entry = by_player_id.setdefault(
                        id_key,
                        {
                            "player_id": player_id,
                            "usernames": set(),
                            "hands_seen": 0,
                            "files": set(),
                        },
                    )
                    entry["usernames"].add(username)
                    entry["files"].add(file_path.name)
                    alias_to_ids.setdefault(username.lower(), set()).add(id_key)
                    if id_key not in seen_ids_in_hand:
                        entry["hands_seen"] += 1
                        seen_ids_in_hand.add(id_key)
        return by_player_id, alias_to_ids, total_hands

    def hands_players(self) -> Dict[str, Any]:
        by_player_id, _alias_to_ids, total_hands = self._uploaded_player_index()
        players = sorted(
            (
                {
                    "selection_key": f"id:{entry['player_id']}",
                    "player_id": entry["player_id"],
                    "username": sorted(entry["usernames"], key=str.lower)[0],
                    "display_name": " / ".join(sorted(entry["usernames"], key=str.lower)),
                    "usernames": sorted(entry["usernames"], key=str.lower),
                    "hands_seen": int(entry["hands_seen"]),
                    "player_ids": [entry["player_id"]],
                }
                for entry in by_player_id.values()
            ),
            key=lambda row: (-row["hands_seen"], row["display_name"].lower()),
        )
        files = self._uploaded_hand_files()
        return {
            "players": players,
            "total_players": len(players),
            "total_hands": int(total_hands),
            "uploaded_files": [f.name for f in files],
            "total_files": len(files),
        }

    def upload_hands(
        self,
        file_items: List[Tuple[str, bytes]],
        *,
        max_total_hands: int | None = None,
        max_hands_per_bucket: int | None = None,
    ) -> Dict[str, Any]:
        if not file_items:
            raise ValueError("No files uploaded")

        total_bytes = 0
        prepared: List[Dict[str, Any]] = []
        for idx, (filename, content) in enumerate(file_items):
            blob = bytes(content or b"")
            if not blob:
                continue
            file_size = len(blob)
            if file_size > self.MAX_UPLOAD_FILE_BYTES:
                raise ValueError(
                    f"File too large: {filename} (max {self.MAX_UPLOAD_FILE_BYTES // (1024 * 1024)}MB each)"
                )
            total_bytes += file_size
            if total_bytes > self.MAX_UPLOAD_BATCH_BYTES:
                raise ValueError(
                    f"Total upload too large (max {self.MAX_UPLOAD_BATCH_BYTES // (1024 * 1024)}MB per upload)"
                )
            safe_name = self._sanitize_upload_filename(filename, idx + 1)
            try:
                decoded = blob.decode("utf-8")
                payload = json.loads(decoded)
            except (UnicodeDecodeError, ValueError) as exc:
                raise ValueError(f"Invalid JSON file: {filename}") from exc

            hands = payload.get("hands", payload if isinstance(payload, list) else [])
            if not isinstance(hands, list):
                raise ValueError(f"Invalid hand payload in {filename}: expected list of hands")

            prepared.append(
                {
                    "safe_name": safe_name,
                    "decoded": decoded,
                    "original_filename": str(filename or ""),
                    "hands_in_file": len(hands),
                }
            )

        if not prepared:
            raise ValueError("No usable JSON files were uploaded")

        saved: List[Dict[str, Any]] = []
        written_paths: List[Path] = []
        for idx, item in enumerate(prepared):
            target_name = f"{int(time.time())}_{idx + 1}_{item['safe_name']}"
            target_path = self._uploaded_hands_dir / target_name
            target_path.write_text(str(item["decoded"]), encoding="utf-8")
            written_paths.append(target_path)
            saved.append(
                {
                    "original_filename": str(item["original_filename"]),
                    "stored_filename": target_name,
                    "hands_in_file": int(item["hands_in_file"]),
                }
            )

        status = self.hands_players()
        def _rollback_uploads() -> Dict[str, Any]:
            for path in written_paths:
                try:
                    path.unlink()
                except OSError:
                    pass
            self._profile_cache.clear()
            return self.hands_players()

        if max_total_hands is not None and int(status.get("total_hands", 0)) > int(max_total_hands):
            status = _rollback_uploads()
            raise ValueError(
                f"Upload exceeds plan limit of {int(max_total_hands)} total hands. "
                f"Current uploaded hands: {int(status.get('total_hands', 0))}."
            )
        if max_hands_per_bucket is not None:
            bucket_limit = int(max_hands_per_bucket)
            violating = []
            for row in status.get("players", []) or []:
                hands_seen = int(row.get("hands_seen", 0))
                if hands_seen > bucket_limit:
                    violating.append(
                        {
                            "name": str(row.get("display_name") or row.get("username") or row.get("selection_key") or "unknown"),
                            "hands_seen": hands_seen,
                        }
                    )
            if violating:
                violating.sort(key=lambda item: item["hands_seen"], reverse=True)
                status = _rollback_uploads()
                top = ", ".join(f"{entry['name']} ({entry['hands_seen']})" for entry in violating[:3])
                raise ValueError(
                    f"Upload exceeds plan limit of {bucket_limit} hands per player bucket. "
                    f"Top bucket(s): {top}."
                )
        self._profile_cache.clear()
        return {
            "saved_files": saved,
            **status,
        }

    def analyzer_players(self) -> List[str]:
        uploaded = self.hands_players().get("players", [])
        return [str(row.get("selection_key") or row.get("username")) for row in uploaded]

    def _hands_snapshot_signature(self) -> str:
        """Stable signature of analyzer hand files used for cache invalidation."""
        files = self._uploaded_hand_files()
        if not files:
            return "missing"
        parts: List[str] = []
        for hand_file in files:
            try:
                st = hand_file.stat()
            except OSError:
                continue
            parts.append(f"{hand_file.name}:{st.st_size}:{st.st_mtime_ns}")
        return "|".join(parts)

    @staticmethod
    def _profile_dict_from_generated(
        profile: Any,
        *,
        key: str,
        name: str,
        source: str,
        include_exploits: bool = True,
    ) -> dict:
        af = profile.postflop.total_aggression_factor
        if af == float("inf") or math.isinf(af):
            af = 6.0
        return {
            "key": key,
            "name": name,
            "source": source,
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
            "exploits": (
                [
                    {
                        "category": e.category,
                        "description": e.description,
                        "counter_strategy": e.counter_strategy,
                    }
                    for e in profile.exploits[:5]
                ]
                if include_exploits
                else []
            ),
        }

    @staticmethod
    def _weighted_average(profiles: Iterable[dict], field: str) -> float:
        rows = list(profiles)
        if not rows:
            return 0.0
        total_w = sum(max(1, int(p.get("hands_analyzed", 0))) for p in rows)
        if total_w <= 0:
            return 0.0
        weighted = sum(float(p.get(field, 0.0)) * max(1, int(p.get("hands_analyzed", 0))) for p in rows)
        return weighted / total_w

    def _resolve_player_ids(self, names: List[str]) -> Tuple[Set[str], List[str], str]:
        by_player_id, alias_to_ids, _total_hands = self._uploaded_player_index()
        if not by_player_id:
            raise ValueError("No uploaded hand files found. Upload PokerNow JSON hand files first.")
        ids: Set[str] = set()
        display: List[str] = []
        seen_bucket_ids: Set[str] = set()
        for raw_name in names:
            token = raw_name.strip()
            token_key = token.lower()
            matched_bucket_ids: Set[str] = set()

            if token_key.startswith("id:"):
                bucket_key = token_key[3:].strip()
                if bucket_key:
                    matched_bucket_ids.add(bucket_key)
            elif token_key in by_player_id:
                matched_bucket_ids.add(token_key)
            else:
                matched_bucket_ids.update(alias_to_ids.get(token_key, set()))

            if not matched_bucket_ids:
                raise ValueError(f"Username or player id not found in uploaded hands: {raw_name}")

            for bucket_id in sorted(matched_bucket_ids):
                if bucket_id in seen_bucket_ids:
                    continue
                entry = by_player_id.get(bucket_id)
                if not entry:
                    continue
                seen_bucket_ids.add(bucket_id)
                ids.add(str(entry["player_id"]))
                names_joined = " / ".join(sorted(entry["usernames"], key=str.lower))
                display.append(names_joined)
        return ids, display, "uploaded_analyzer"

    def analyzer_profile(
        self,
        player_name: str,
        *,
        include_exploits: bool = True,
        max_usernames: int | None = None,
    ) -> dict:
        names = self._parse_names_input(player_name)
        if not names:
            raise ValueError("player_name is required")
        if max_usernames is not None and len(names) > int(max_usernames):
            raise ValueError(
                f"Too many usernames selected ({len(names)}). "
                f"Your plan allows up to {int(max_usernames)} aliases per profile."
            )
        key = "|".join(sorted(n.lower() for n in names))
        cache_key = f"{'x' if include_exploits else 'no-x'}::{key}"
        hands_snapshot = self._hands_snapshot_signature()
        cached = self._profile_cache.get(cache_key)
        if cached and cached.get("snapshot") == hands_snapshot:
            profile = cached.get("profile")
            if isinstance(profile, dict):
                return profile

        active_files = self._uploaded_hand_files()
        if not active_files:
            raise ValueError("No hand files available. Upload JSON hand histories first.")
        player_ids, display_names, source = self._resolve_player_ids(names)

        from parser import load_hands  # local import to avoid startup cost
        from stats.aggregate import generate_profile

        all_hands = []
        for hand_file in active_files:
            all_hands.extend(load_hands(hand_file))
        if not all_hands:
            raise ValueError("No hands loaded from available hand files")

        per_player_profiles: List[dict] = []
        for player_id in sorted(player_ids):
            generated = generate_profile(all_hands, player_id)
            if generated.hands_analyzed <= 0:
                continue
            per_player_profiles.append(
                self._profile_dict_from_generated(
                    generated,
                    key=player_id,
                    name=player_id,
                    source=source,
                    include_exploits=include_exploits,
                )
            )
        if not per_player_profiles:
            requested = ", ".join(display_names)
            raise ValueError(f"No analyzable hands found for: {requested}")

        if len(per_player_profiles) == 1:
            single = dict(per_player_profiles[0])
            single["key"] = key
            single["name"] = display_names[0].upper()
            single["selected_usernames"] = display_names
            single["player_ids"] = sorted(player_ids)
            if not include_exploits:
                single["exploits"] = []
            built = single
        else:
            style_counter: Counter[str] = Counter()
            tendency_counter: Counter[str] = Counter()
            exploit_counter: Counter[Tuple[str, str, str]] = Counter()
            total_hands = 0

            for profile in per_player_profiles:
                w = max(1, int(profile.get("hands_analyzed", 0)))
                total_hands += w
                style_counter[str(profile.get("style_label") or "Unknown")] += w
                for tendency in profile.get("tendencies", []):
                    tendency_counter[str(tendency)] += w
                for exploit in profile.get("exploits", []):
                    exploit_counter[
                        (
                            str(exploit.get("category", "postflop")),
                            str(exploit.get("description", "")),
                            str(exploit.get("counter_strategy", "")),
                        )
                    ] += w

            exploits = []
            if include_exploits:
                exploits = [
                    {
                        "category": category,
                        "description": description,
                        "counter_strategy": counter,
                    }
                    for (category, description, counter), _ in exploit_counter.most_common(5)
                    if description
                ]
            built = {
                "key": key,
                "name": " + ".join(name.upper() for name in display_names),
                "source": source,
                "style_label": style_counter.most_common(1)[0][0] if style_counter else "Unknown",
                "hands_analyzed": int(total_hands),
                "vpip": round(self._weighted_average(per_player_profiles, "vpip"), 4),
                "pfr": round(self._weighted_average(per_player_profiles, "pfr"), 4),
                "three_bet": round(self._weighted_average(per_player_profiles, "three_bet"), 4),
                "fold_to_3bet": round(self._weighted_average(per_player_profiles, "fold_to_3bet"), 4),
                "limp_rate": round(self._weighted_average(per_player_profiles, "limp_rate"), 4),
                "af": round(self._weighted_average(per_player_profiles, "af"), 3),
                "aggression_frequency": round(self._weighted_average(per_player_profiles, "aggression_frequency"), 4),
                "flop_cbet": round(self._weighted_average(per_player_profiles, "flop_cbet"), 4),
                "turn_cbet": round(self._weighted_average(per_player_profiles, "turn_cbet"), 4),
                "river_cbet": round(self._weighted_average(per_player_profiles, "river_cbet"), 4),
                "double_barrel": round(self._weighted_average(per_player_profiles, "double_barrel"), 4),
                "triple_barrel": round(self._weighted_average(per_player_profiles, "triple_barrel"), 4),
                "check_raise": round(self._weighted_average(per_player_profiles, "check_raise"), 4),
                "wtsd": round(self._weighted_average(per_player_profiles, "wtsd"), 4),
                "w_sd": round(self._weighted_average(per_player_profiles, "w_sd"), 4),
                "tendencies": [text for text, _ in tendency_counter.most_common(8)],
                "exploits": exploits,
                "selected_usernames": display_names,
                "player_ids": sorted(player_ids),
                "players_aggregated": len(per_player_profiles),
            }

        built.setdefault("selected_usernames", display_names)
        built.setdefault("player_ids", sorted(player_ids))
        built.setdefault("players_aggregated", len(per_player_profiles))
        self._profile_cache[cache_key] = {
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
                "analyzer_players": self.analyzer_players(),
                "hands_status": self.hands_players(),
                "defaults": {
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
        requested_names = (
            payload.get("analyzer_players")
            or payload.get("opponent_usernames")
            or payload.get("analyzer_player")
        )
        if isinstance(requested_names, list):
            joined_names = ",".join(str(v).strip() for v in requested_names if str(v).strip())
        else:
            joined_names = str(requested_names or "").strip()
        if not joined_names:
            raise ValueError("Select at least one opponent username from uploaded hand files")
        opponent_profile = self.analyzer_profile(joined_names)

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
