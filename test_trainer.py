#!/usr/bin/env python3
"""Smoke tests for trainer scenario generation and EV evaluation."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from trainer.poker_theory import (
    break_even_bluff_fold_frequency,
    minimum_defense_frequency,
    polarized_bluff_share,
    required_equity_to_call,
)
from trainer.service import TrainerService


def test_trainer_generate_and_evaluate():
    db_path = Path("trainer/data/test_trainer.db")
    if db_path.exists():
        db_path.unlink()

    service = TrainerService(db_path=db_path)
    scenario = service.generate(
        {
            "num_players": 6,
            "street": "flop",
            "node_type": "single_raised_pot",
            "action_context": "facing_bet_and_call",
            "hero_position": "BTN",
            "players_in_hand": 3,
            "equal_stacks": True,
            "default_stack_bb": 100,
            "hero_profile": {
                "vpip": 34,
                "pfr": 24,
                "af": 3.1,
                "three_bet": 10,
                "fold_to_3bet": 57,
            },
            "seed": 101,
        }
    )

    assert scenario["hero_position"] == "BTN"
    assert scenario["players_in_hand"] >= 2
    assert "legal_actions" in scenario
    assert "hero_profile" in scenario
    assert "position_guidance" in scenario

    reloaded = service.get_scenario(scenario["scenario_id"])
    assert reloaded["scenario_id"] == scenario["scenario_id"]

    if "raise" in scenario["legal_actions"]:
        decision = {
            "action": "raise",
            "size_bb": scenario["raise_size_options_bb"][0],
            "intent": "value",
        }
    elif "bet" in scenario["legal_actions"]:
        decision = {
            "action": "bet",
            "size_bb": scenario["bet_size_options_bb"][0],
            "intent": "value",
        }
    else:
        decision = {"action": scenario["legal_actions"][0]}

    result = service.evaluate(
        {
            "scenario_id": scenario["scenario_id"],
            "decision": decision,
            "free_response": "test run",
            "simulations": 120,
        }
    )
    evaluation = result["evaluation"]
    assert evaluation["scenario_id"] == scenario["scenario_id"]
    assert "best_action" in evaluation
    assert "chosen_action" in evaluation
    assert isinstance(evaluation["action_table"], list)
    assert len(evaluation["action_table"]) >= 2
    assert "leak_report" in evaluation
    assert "factor_breakdown" in evaluation["leak_report"]
    assert "hero_profile_analysis" in evaluation["leak_report"]

    progress = service.progress()
    assert progress["totals"]["attempts"] >= 1

    if db_path.exists():
        db_path.unlink()


def test_randomization_toggles():
    db_path = Path("trainer/data/test_trainer_random.db")
    if db_path.exists():
        db_path.unlink()

    service = TrainerService(db_path=db_path)
    scenario = service.generate(
        {
            "num_players": 6,
            "street": "flop",
            "node_type": "single_raised_pot",
            "action_context": "facing_bet",
            "hero_position": "CO",
            "players_in_hand": 3,
            "equal_stacks": True,
            "default_stack_bb": 100,
            "hero_profile": {"vpip": 22, "pfr": 19, "af": 2.2, "three_bet": 7, "fold_to_3bet": 55},
            "randomize_hero_profile": True,
            "randomize_archetypes": True,
            "seed": 2026,
        }
    )

    assert scenario["randomization"]["hero_profile"] is True
    assert scenario["randomization"]["archetypes"] is True

    hero_profile = scenario["hero_profile"]
    assert 0.08 <= hero_profile["vpip"] <= 0.65
    assert 0.05 <= hero_profile["pfr"] <= 0.50
    assert 0.4 <= hero_profile["af"] <= 8.0

    cleared = service.clear_saved_hands()
    assert cleared["scenarios_deleted"] >= 1
    assert cleared["attempts_deleted"] >= 0

    if db_path.exists():
        db_path.unlink()


def test_postflop_order_btn_vs_blinds_and_context_resolution():
    db_path = Path("trainer/data/test_trainer_action_order.db")
    if db_path.exists():
        db_path.unlink()

    service = TrainerService(db_path=db_path)

    btn_spot = service.generate(
        {
            "num_players": 3,
            "street": "flop",
            "node_type": "single_raised_pot",
            "action_context": "facing_bet_and_call",
            "hero_position": "BTN",
            "players_in_hand": 3,
            "equal_stacks": True,
            "default_stack_bb": 100,
            "seed": 777,
        }
    )

    history = btn_spot["action_history"]
    bet_line = next((line for line in history if " bets " in line), "")
    call_line = next((line for line in history if " calls " in line), "")
    assert btn_spot["action_context"] == "facing_bet_and_call"
    assert bet_line.startswith("SB bets")
    assert call_line.startswith("BB calls")

    sb_spot = service.generate(
        {
            "num_players": 3,
            "street": "flop",
            "node_type": "single_raised_pot",
            "action_context": "facing_bet_and_call",
            "hero_position": "SB",
            "players_in_hand": 3,
            "equal_stacks": True,
            "default_stack_bb": 100,
            "seed": 888,
        }
    )

    assert sb_spot["action_context"] == "checked_to_hero"
    assert sb_spot["to_call_bb"] == 0
    assert sb_spot["legal_actions"] == ["check", "bet"]
    assert "Action checks to Hero." in sb_spot["action_history"]

    if db_path.exists():
        db_path.unlink()


def test_poker_theory_formula_sanity():
    req = required_equity_to_call(pot_before_call=10.0, call_amount=5.0)
    assert round(req, 4) == 0.3333

    mdf = minimum_defense_frequency(pot_before_bet=10.0, bet_size=5.0)
    assert round(mdf, 4) == 0.6667

    be_bluff = break_even_bluff_fold_frequency(risk=5.0, reward=10.0)
    assert round(be_bluff, 4) == 0.3333

    bluff_share = polarized_bluff_share(0.75)
    assert round(bluff_share, 4) == 0.4286


def test_live_play_session_basic():
    db_path = Path("trainer/data/test_trainer_live.db")
    if db_path.exists():
        db_path.unlink()

    service = TrainerService(db_path=db_path)
    started = service.live_start(
        {
            "opponent_source": "preset",
            "preset_key": "charlie",
            "starting_stack_bb": 100,
            "seed": 77,
        }
    )
    session_id = started["session_id"]
    assert session_id.startswith("live_")
    assert started["match"]["opponent"]["name"] == "CHARLIE"
    assert len(started["hand"]["legal_actions"]) >= 1
    assert "villain_range_summary" in started["hand"]
    assert "top_weighted_hands" in started["hand"]["villain_range_summary"]
    assert "hero_image_score" in started["hand"]["villain_range_summary"]
    assert len(started["hand"]["villain_range_summary"]["top_weighted_hands"]) >= 4

    hand = started["hand"]
    action = hand["legal_actions"][0]
    payload = {"session_id": session_id, "action": action}
    if action in {"bet", "raise"}:
        payload["size_bb"] = hand["size_options_bb"][0]
        payload["intent"] = "value"
    acted = service.live_action(payload)
    assert acted["session_id"] == session_id
    assert "hand" in acted

    dealt = service.live_new_hand({"session_id": session_id})
    assert dealt["hand"]["hand_no"] >= 2

    if db_path.exists():
        db_path.unlink()


def test_analyzer_profile_cache_invalidates_when_hands_change():
    db_path = Path("trainer/data/test_trainer_profile_cache.db")
    if db_path.exists():
        db_path.unlink()

    service = TrainerService(db_path=db_path)

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        hands_dir = root / "hands"
        hands_dir.mkdir(parents=True, exist_ok=True)
        (hands_dir / "h1.json").write_text("{}", encoding="utf-8")
        (root / "names.csv").write_text("charlie\nplayer_charlie\n", encoding="utf-8")
        service._root_dir = root

        fake_profile = SimpleNamespace(
            play_style=SimpleNamespace(value="Loose-Passive (Calling Station)"),
            hands_analyzed=12,
            preflop=SimpleNamespace(
                vpip=0.55,
                pfr=0.20,
                three_bet_frequency=0.08,
                fold_to_3bet=0.0,
                limp_rate=0.35,
            ),
            postflop=SimpleNamespace(
                total_aggression_factor=0.9,
                total_aggression_frequency=0.30,
                flop=SimpleNamespace(cbet_frequency=0.70),
                turn=SimpleNamespace(cbet_frequency=0.20),
                river=SimpleNamespace(cbet_frequency=0.10),
                double_barrel_frequency=0.45,
                triple_barrel_frequency=0.20,
                check_raise_frequency=0.08,
            ),
            showdown=SimpleNamespace(
                wtsd=0.58,
                w_sd=0.66,
            ),
            tendencies=[],
            exploits=[],
        )

        counters = {"load_hands": 0, "generate_profile": 0}

        def fake_load_hands(_path):
            counters["load_hands"] += 1
            return [{"id": counters["load_hands"]}]

        def fake_generate_profile(_hands, _player_id):
            counters["generate_profile"] += 1
            return fake_profile

        with patch("parser.load_hands", side_effect=fake_load_hands), patch(
            "stats.aggregate.generate_profile", side_effect=fake_generate_profile
        ):
            _first = service.analyzer_profile("charlie")
            _second = service.analyzer_profile("charlie")
            assert counters["load_hands"] == 1
            assert counters["generate_profile"] == 1

            (hands_dir / "h2.json").write_text("{}", encoding="utf-8")
            _third = service.analyzer_profile("charlie")
            assert counters["load_hands"] == 3
            assert counters["generate_profile"] == 2

    if db_path.exists():
        db_path.unlink()
