"""SQLite persistence for scenarios and training attempts."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class TrainerStore:
    """Persistence layer for trainer state and progress tracking."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scenarios (
                    scenario_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS attempts (
                    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    hero_position TEXT NOT NULL,
                    street TEXT NOT NULL,
                    node_type TEXT NOT NULL,
                    players_in_hand INTEGER NOT NULL,
                    chosen_action TEXT NOT NULL,
                    chosen_size_bb REAL,
                    chosen_intent TEXT,
                    chosen_ev_bb REAL NOT NULL,
                    best_action TEXT NOT NULL,
                    best_ev_bb REAL NOT NULL,
                    ev_loss_bb REAL NOT NULL,
                    verdict TEXT NOT NULL,
                    mistake_tags_json TEXT NOT NULL,
                    free_response TEXT,
                    evaluation_json TEXT NOT NULL,
                    FOREIGN KEY (scenario_id) REFERENCES scenarios (scenario_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_attempts_created_at ON attempts(created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_attempts_position ON attempts(hero_position)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_attempts_street ON attempts(street)"
            )

    def save_scenario(self, scenario: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO scenarios (scenario_id, created_at, payload_json)
                VALUES (?, ?, ?)
                """,
                (
                    scenario["scenario_id"],
                    scenario.get("created_at") or datetime.now(timezone.utc).isoformat(),
                    json.dumps(scenario),
                ),
            )

    def get_scenario(self, scenario_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM scenarios WHERE scenario_id = ?",
                (scenario_id,),
            ).fetchone()
            if not row:
                return None
            return json.loads(row["payload_json"])

    def save_attempt(self, scenario: dict, decision: dict, evaluation: dict, free_response: str) -> int:
        chosen = evaluation["chosen_action"]
        best = evaluation["best_action"]
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO attempts (
                    created_at,
                    scenario_id,
                    hero_position,
                    street,
                    node_type,
                    players_in_hand,
                    chosen_action,
                    chosen_size_bb,
                    chosen_intent,
                    chosen_ev_bb,
                    best_action,
                    best_ev_bb,
                    ev_loss_bb,
                    verdict,
                    mistake_tags_json,
                    free_response,
                    evaluation_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    scenario["scenario_id"],
                    scenario["hero_position"],
                    scenario["street"],
                    scenario["node_type"],
                    int(scenario.get("players_in_hand", 0)),
                    chosen["action"],
                    chosen.get("size_bb"),
                    chosen.get("intent"),
                    float(chosen["ev_bb"]),
                    best["label"],
                    float(best["ev_bb"]),
                    float(evaluation["ev_loss_bb"]),
                    evaluation["verdict"],
                    json.dumps(evaluation.get("mistake_tags", [])),
                    free_response.strip(),
                    json.dumps(
                        {
                            "decision": decision,
                            "evaluation": evaluation,
                        }
                    ),
                ),
            )
            return int(cur.lastrowid)

    def _by_dimension(self, column: str) -> List[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    {column} AS label,
                    COUNT(*) AS attempts,
                    AVG(ev_loss_bb) AS avg_ev_loss_bb,
                    AVG(CASE WHEN ev_loss_bb <= 0.2 THEN 1.0 ELSE 0.0 END) AS accuracy
                FROM attempts
                GROUP BY {column}
                ORDER BY attempts DESC, avg_ev_loss_bb ASC
                """
            ).fetchall()
            return [
                {
                    "label": row["label"],
                    "attempts": int(row["attempts"]),
                    "avg_ev_loss_bb": round(float(row["avg_ev_loss_bb"] or 0.0), 3),
                    "accuracy": round(float(row["accuracy"] or 0.0), 3),
                }
                for row in rows
            ]

    def progress_summary(self) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS attempts,
                    AVG(ev_loss_bb) AS avg_ev_loss_bb,
                    AVG(CASE WHEN ev_loss_bb <= 0.2 THEN 1.0 ELSE 0.0 END) AS accuracy,
                    AVG(chosen_ev_bb) AS avg_chosen_ev_bb
                FROM attempts
                """
            ).fetchone()
            latest = conn.execute(
                """
                SELECT
                    attempt_id,
                    created_at,
                    scenario_id,
                    hero_position,
                    street,
                    chosen_action,
                    chosen_size_bb,
                    chosen_intent,
                    chosen_ev_bb,
                    best_action,
                    best_ev_bb,
                    ev_loss_bb,
                    verdict
                FROM attempts
                ORDER BY attempt_id DESC
                LIMIT 20
                """
            ).fetchall()

        out = {
            "totals": {
                "attempts": int(row["attempts"] or 0),
                "avg_ev_loss_bb": round(float(row["avg_ev_loss_bb"] or 0.0), 3),
                "accuracy": round(float(row["accuracy"] or 0.0), 3),
                "avg_chosen_ev_bb": round(float(row["avg_chosen_ev_bb"] or 0.0), 3),
            },
            "by_position": self._by_dimension("hero_position"),
            "by_street": self._by_dimension("street"),
            "by_node_type": self._by_dimension("node_type"),
            "recent_attempts": [
                {
                    "attempt_id": int(r["attempt_id"]),
                    "created_at": r["created_at"],
                    "scenario_id": r["scenario_id"],
                    "hero_position": r["hero_position"],
                    "street": r["street"],
                    "chosen_action": r["chosen_action"],
                    "chosen_size_bb": None if r["chosen_size_bb"] is None else round(float(r["chosen_size_bb"]), 2),
                    "chosen_intent": r["chosen_intent"],
                    "chosen_ev_bb": round(float(r["chosen_ev_bb"]), 3),
                    "best_action": r["best_action"],
                    "best_ev_bb": round(float(r["best_ev_bb"]), 3),
                    "ev_loss_bb": round(float(r["ev_loss_bb"]), 3),
                    "verdict": r["verdict"],
                }
                for r in latest
            ],
        }
        return out

    def clear_saved_hands(self) -> dict:
        """Delete all stored scenarios and attempts."""
        with self._connect() as conn:
            attempts_count = conn.execute("SELECT COUNT(*) AS c FROM attempts").fetchone()["c"]
            scenarios_count = conn.execute("SELECT COUNT(*) AS c FROM scenarios").fetchone()["c"]
            conn.execute("DELETE FROM attempts")
            conn.execute("DELETE FROM scenarios")
        return {
            "attempts_deleted": int(attempts_count or 0),
            "scenarios_deleted": int(scenarios_count or 0),
        }
