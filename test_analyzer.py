#!/usr/bin/env python3
"""
Comprehensive test suite for the Poker Analyzer.

Tests all modules: models, parser, and statistics calculations.
Run with: python test_analyzer.py
"""

import sys
import json
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent))

from models import (
    ActionType, Street, HandStrength, 
    PlayerAction, PlayerInHand, ParsedHand, HandResult,
    parse_hand_strength
)
from parser import HandParser, load_hands
from stats.preflop import PreflopAnalyzer
from stats.postflop import PostflopAnalyzer
from stats.showdown import ShowdownAnalyzer
from stats.aggregate import ProfileAnalyzer, PlayStyle


class TestResults:
    """Track test results."""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def ok(self, name: str):
        self.passed += 1
        print(f"  ✓ {name}")
    
    def fail(self, name: str, message: str):
        self.failed += 1
        self.errors.append(f"{name}: {message}")
        print(f"  ✗ {name}: {message}")
    
    def summary(self):
        total = self.passed + self.failed
        print()
        print("=" * 50)
        print(f"Results: {self.passed}/{total} tests passed")
        if self.errors:
            print("\nFailures:")
            for error in self.errors:
                print(f"  - {error}")
        print("=" * 50)
        return self.failed == 0


def assert_eq(actual, expected, name: str, results: TestResults):
    """Assert equality with nice error messages."""
    if actual == expected:
        results.ok(name)
    else:
        results.fail(name, f"expected {expected}, got {actual}")


def assert_close(actual, expected, name: str, results: TestResults, tolerance=0.01):
    """Assert float equality within tolerance."""
    if abs(actual - expected) <= tolerance:
        results.ok(name)
    else:
        results.fail(name, f"expected {expected}±{tolerance}, got {actual}")


def assert_true(condition, name: str, results: TestResults):
    """Assert condition is true."""
    if condition:
        results.ok(name)
    else:
        results.fail(name, "condition was False")


# ============================================================
# TEST DATA
# ============================================================

def create_sample_hand_data():
    """Create sample hand data for testing."""
    return {
        "hands": [
            # Hand 1: Player A opens, B calls, A c-bets, B folds
            {
                "id": "hand_001",
                "dealerSeat": 0,
                "players": [
                    {"id": "player_A", "seat": 0, "stack": 1000},
                    {"id": "player_B", "seat": 1, "stack": 1000},
                    {"id": "player_C", "seat": 2, "stack": 1000},
                ],
                "events": [
                    {"payload": {"type": 3, "seat": 1, "amount": 5}},   # SB
                    {"payload": {"type": 2, "seat": 2, "amount": 10}},  # BB
                    {"payload": {"type": 8, "seat": 0, "amount": 30}},  # A raises
                    {"payload": {"type": 7, "seat": 1, "amount": 25}},  # B calls
                    {"payload": {"type": 11, "seat": 2}},               # C folds
                    {"payload": {"type": 9, "cards": ["Ah", "Kd", "7c"]}},  # Flop
                    {"payload": {"type": 8, "seat": 0, "amount": 45}},  # A c-bets
                    {"payload": {"type": 11, "seat": 1}},               # B folds
                    {"payload": {"type": 10, "seat": 0, "amount": 65}}, # A wins
                ]
            },
            # Hand 2: Player B opens, A 3-bets, B folds
            {
                "id": "hand_002", 
                "dealerSeat": 1,
                "players": [
                    {"id": "player_A", "seat": 0, "stack": 1000},
                    {"id": "player_B", "seat": 1, "stack": 1000},
                    {"id": "player_C", "seat": 2, "stack": 1000},
                ],
                "events": [
                    {"payload": {"type": 3, "seat": 2, "amount": 5}},   # SB
                    {"payload": {"type": 2, "seat": 0, "amount": 10}},  # BB
                    {"payload": {"type": 8, "seat": 1, "amount": 30}},  # B raises
                    {"payload": {"type": 8, "seat": 2, "amount": 90}},  # C 3-bets
                    {"payload": {"type": 11, "seat": 0}},               # A folds
                    {"payload": {"type": 11, "seat": 1}},               # B folds to 3bet
                    {"payload": {"type": 10, "seat": 2, "amount": 45}}, # C wins
                ]
            },
            # Hand 3: Showdown - A vs B, A wins with two pair
            {
                "id": "hand_003",
                "dealerSeat": 2,
                "players": [
                    {"id": "player_A", "seat": 0, "stack": 1000, "cards": ["Kh", "Kd"]},
                    {"id": "player_B", "seat": 1, "stack": 1000, "cards": ["Qh", "Jh"]},
                    {"id": "player_C", "seat": 2, "stack": 1000},
                ],
                "events": [
                    {"payload": {"type": 3, "seat": 0, "amount": 5}},   # SB
                    {"payload": {"type": 2, "seat": 1, "amount": 10}},  # BB
                    {"payload": {"type": 8, "seat": 2, "amount": 30}},  # C raises
                    {"payload": {"type": 7, "seat": 0, "amount": 25}},  # A calls
                    {"payload": {"type": 7, "seat": 1, "amount": 20}},  # B calls
                    {"payload": {"type": 9, "cards": ["Ks", "7h", "2d"]}},  # Flop
                    {"payload": {"type": 0, "seat": 0}},                # A checks
                    {"payload": {"type": 0, "seat": 1}},                # B checks
                    {"payload": {"type": 8, "seat": 2, "amount": 60}},  # C bets
                    {"payload": {"type": 7, "seat": 0, "amount": 60}},  # A calls
                    {"payload": {"type": 11, "seat": 1}},               # B folds
                    {"payload": {"type": 9, "cards": ["7c"]}},          # Turn
                    {"payload": {"type": 8, "seat": 0, "amount": 100}}, # A bets
                    {"payload": {"type": 7, "seat": 2, "amount": 100}}, # C calls
                    {"payload": {"type": 9, "cards": ["2s"]}},          # River
                    {"payload": {"type": 8, "seat": 0, "amount": 150}}, # A bets (river)
                    {"payload": {"type": 7, "seat": 2, "amount": 150}}, # C calls
                    {"payload": {"type": 10, "seat": 0, "amount": 660, 
                                 "handDescription": "Full House", "cards": ["Kh", "Kd"]}},
                ]
            },
            # Hand 4: A limps, B raises, A calls
            {
                "id": "hand_004",
                "dealerSeat": 0,
                "players": [
                    {"id": "player_A", "seat": 0, "stack": 1000},
                    {"id": "player_B", "seat": 1, "stack": 1000},
                ],
                "events": [
                    {"payload": {"type": 3, "seat": 1, "amount": 5}},   # SB
                    {"payload": {"type": 2, "seat": 0, "amount": 10}},  # A BB
                    {"payload": {"type": 7, "seat": 1, "amount": 5}},   # B limps (calls BB)
                    {"payload": {"type": 0, "seat": 0}},                # A checks
                    {"payload": {"type": 9, "cards": ["5h", "5d", "5c"]}},  # Flop
                    {"payload": {"type": 0, "seat": 1}},                # B checks
                    {"payload": {"type": 0, "seat": 0}},                # A checks
                    {"payload": {"type": 9, "cards": ["2h"]}},          # Turn
                    {"payload": {"type": 0, "seat": 1}},                # B checks
                    {"payload": {"type": 0, "seat": 0}},                # A checks
                    {"payload": {"type": 9, "cards": ["3h"]}},          # River
                    {"payload": {"type": 0, "seat": 1}},                # B checks
                    {"payload": {"type": 0, "seat": 0}},                # A checks
                    {"payload": {"type": 10, "seat": 0, "amount": 20, 
                                 "handDescription": "High Card"}},
                ]
            },
        ]
    }


# ============================================================
# TESTS
# ============================================================

def test_models(results: TestResults):
    """Test model classes and enums."""
    print("\n--- Testing Models ---")
    
    # ActionType enum
    assert_eq(ActionType.FOLD.value, 11, "ActionType.FOLD value", results)
    assert_eq(ActionType.BET_RAISE.value, 8, "ActionType.BET_RAISE value", results)
    assert_eq(ActionType.CHECK.value, 0, "ActionType.CHECK value", results)
    
    # Street enum
    assert_eq(Street.PREFLOP.value, "preflop", "Street.PREFLOP value", results)
    assert_eq(Street.RIVER.value, "river", "Street.RIVER value", results)
    
    # HandStrength enum
    assert_eq(HandStrength.PAIR.value, 2, "HandStrength.PAIR value", results)
    assert_eq(HandStrength.FULL_HOUSE.value, 7, "HandStrength.FULL_HOUSE value", results)
    
    # parse_hand_strength function
    assert_eq(parse_hand_strength("Two Pair"), HandStrength.TWO_PAIR, "parse 'Two Pair'", results)
    assert_eq(parse_hand_strength("flush"), HandStrength.FLUSH, "parse 'flush'", results)
    assert_eq(parse_hand_strength("Full House"), HandStrength.FULL_HOUSE, "parse 'Full House'", results)
    assert_eq(parse_hand_strength(""), None, "parse empty string", results)
    
    # PlayerAction properties
    action = PlayerAction(
        player_id="test",
        seat=0,
        action_type=ActionType.BET_RAISE,
        street=Street.FLOP,
        amount=50,
        pot_before=100
    )
    assert_true(action.is_aggressive, "BET_RAISE is aggressive", results)
    assert_true(action.is_voluntary, "BET_RAISE is voluntary", results)
    assert_close(action.pot_ratio, 0.5, "pot ratio calculation", results)
    
    # Check action
    check_action = PlayerAction(
        player_id="test",
        seat=0,
        action_type=ActionType.CHECK,
        street=Street.FLOP
    )
    assert_true(not check_action.is_aggressive, "CHECK is not aggressive", results)
    assert_true(not check_action.is_voluntary, "CHECK is not voluntary", results)


def test_parser(results: TestResults):
    """Test the hand parser."""
    print("\n--- Testing Parser ---")
    
    data = create_sample_hand_data()
    parser = HandParser()
    hands = parser.parse_data(data)
    
    assert_eq(len(hands), 4, "parsed 4 hands", results)
    assert_eq(len(parser.errors), 0, "no parsing errors", results)
    
    # Test first hand structure
    hand1 = hands[0]
    assert_eq(hand1.hand_id, "hand_001", "hand 1 ID", results)
    assert_eq(len(hand1.players), 3, "hand 1 has 3 players", results)
    assert_eq(hand1.dealer_seat, 0, "hand 1 dealer seat", results)
    assert_eq(hand1.small_blind, 5, "hand 1 small blind", results)
    assert_eq(hand1.big_blind, 10, "hand 1 big blind", results)
    
    # Test board parsing
    assert_eq(len(hand1.board), 3, "hand 1 board has 3 cards (flop only)", results)
    
    # Test player lookup
    player_a = hand1.get_player_by_id("player_A")
    assert_true(player_a is not None, "found player_A", results)
    assert_eq(player_a.seat, 0, "player_A seat", results)
    
    # Test action parsing
    preflop_actions = hand1.get_actions_on_street(Street.PREFLOP)
    assert_true(len(preflop_actions) >= 3, "preflop has at least 3 actions", results)
    
    flop_actions = hand1.get_actions_on_street(Street.FLOP)
    assert_eq(len(flop_actions), 2, "flop has 2 actions", results)
    
    # Test hand 3 showdown parsing
    hand3 = hands[2]
    assert_eq(len(hand3.board), 5, "hand 3 has full board", results)
    assert_true("player_A" in hand3.results, "player_A has result", results)
    assert_true(hand3.results["player_A"].won_pot, "player_A won", results)
    assert_eq(hand3.results["player_A"].hand_strength, HandStrength.FULL_HOUSE, 
              "player_A had full house", results)


def test_preflop_stats(results: TestResults):
    """Test preflop statistics calculation."""
    print("\n--- Testing Preflop Stats ---")
    
    data = create_sample_hand_data()
    parser = HandParser()
    hands = parser.parse_data(data)
    
    analyzer = PreflopAnalyzer()
    
    # Test player A
    stats_a = analyzer.analyze(hands, "player_A")
    
    assert_eq(stats_a.hands_played, 4, "A played 4 hands", results)
    
    # A: hand1 raised, hand2 folded, hand3 called, hand4 checked (BB)
    # VPIP = raised or called = 2/4 = 0.5
    # PFR = raised = 1/4 = 0.25
    assert_eq(stats_a.vpip_count, 2, "A vpip count", results)
    assert_eq(stats_a.pfr_count, 1, "A pfr count", results)
    assert_close(stats_a.vpip, 0.5, "A VPIP", results)
    assert_close(stats_a.pfr, 0.25, "A PFR", results)
    
    # Test player B
    stats_b = analyzer.analyze(hands, "player_B")
    
    # B: hand1 called, hand2 raised then folded to 3bet, hand3 called, hand4 limped
    assert_eq(stats_b.hands_played, 4, "B played 4 hands", results)
    assert_true(stats_b.vpip_count >= 3, "B vpip count >= 3", results)  # called/raised/limped


def test_postflop_stats(results: TestResults):
    """Test postflop statistics calculation."""
    print("\n--- Testing Postflop Stats ---")
    
    data = create_sample_hand_data()
    parser = HandParser()
    hands = parser.parse_data(data)
    
    analyzer = PostflopAnalyzer()
    
    # Test player A
    stats_a = analyzer.analyze(hands, "player_A")
    
    # A saw flop in: hand1 (c-bet), hand3 (check-call then bet turn/river), hand4 (check)
    assert_true(stats_a.flop.opportunities >= 2, "A saw flop at least twice", results)
    
    # A c-bet in hand 1
    assert_true(stats_a.flop.cbets_made >= 1, "A c-bet at least once", results)
    
    # A made river bet in hand 3
    assert_true(stats_a.river.bets + stats_a.river.raises >= 1, 
                "A bet river at least once", results)


def test_showdown_stats(results: TestResults):
    """Test showdown statistics calculation."""
    print("\n--- Testing Showdown Stats ---")
    
    data = create_sample_hand_data()
    parser = HandParser()
    hands = parser.parse_data(data)
    
    analyzer = ShowdownAnalyzer()
    
    # Test player A
    stats_a = analyzer.analyze(hands, "player_A")
    
    # A went to showdown in hand 3 and hand 4, won both
    assert_true(stats_a.saw_showdown >= 2, "A saw showdown at least twice", results)
    assert_true(stats_a.won_at_showdown >= 2, "A won at showdown at least twice", results)
    
    # Check hand strength tracking (hand 3 was full house = 7)
    assert_true(len(stats_a.showdown_strengths) >= 1, "A has showdown strength data", results)
    if stats_a.showdown_strengths:
        assert_true(7 in stats_a.showdown_strengths or 1 in stats_a.showdown_strengths,
                    "A showdown strength includes full house (7) or high card (1)", results)


def test_aggregate_profile(results: TestResults):
    """Test aggregate profile generation."""
    print("\n--- Testing Aggregate Profile ---")
    
    data = create_sample_hand_data()
    parser = HandParser()
    hands = parser.parse_data(data)
    
    analyzer = ProfileAnalyzer()
    profile = analyzer.analyze(hands, "player_A")
    
    # Check basic profile structure
    assert_eq(profile.player_id, "player_A", "profile player ID", results)
    assert_eq(profile.hands_analyzed, 4, "profile hands analyzed", results)
    
    # Check that stats are populated
    assert_true(profile.preflop is not None, "preflop stats populated", results)
    assert_true(profile.postflop is not None, "postflop stats populated", results)
    assert_true(profile.showdown is not None, "showdown stats populated", results)
    
    # With only 4 hands, confidence should be low
    assert_eq(profile.sample_confidence, "Low", "low sample confidence", results)
    
    # Play style should be classified (though possibly UNKNOWN with few hands)
    assert_true(isinstance(profile.play_style, PlayStyle), "play style is PlayStyle enum", results)


def test_edge_cases(results: TestResults):
    """Test edge cases and error handling."""
    print("\n--- Testing Edge Cases ---")
    
    parser = HandParser()
    
    # Empty data
    hands = parser.parse_data({"hands": []})
    assert_eq(len(hands), 0, "empty hands list", results)
    
    # Missing player ID
    data = create_sample_hand_data()
    hands = parser.parse_data(data)
    
    analyzer = PreflopAnalyzer()
    stats = analyzer.analyze(hands, "nonexistent_player")
    assert_eq(stats.hands_played, 0, "nonexistent player has 0 hands", results)
    
    # Hand with no events
    data = {"hands": [{"id": "empty", "dealerSeat": 0, "players": [], "events": []}]}
    hands = parser.parse_data(data)
    # Should not crash, may produce warning
    assert_eq(len(parser.errors), 0, "no errors on empty events", results)


def test_position_tracking(results: TestResults):
    """Test position calculation and stats by position."""
    print("\n--- Testing Position Tracking ---")
    
    data = create_sample_hand_data()
    parser = HandParser()
    hands = parser.parse_data(data)
    
    # Check position assignment in parsed hands
    hand1 = hands[0]
    player_a = hand1.get_player_by_id("player_A")
    
    # In hand1, dealer is seat 0 (player A), so A should be position 0
    assert_eq(player_a.position, 0, "player_A is dealer (pos 0) in hand 1", results)
    assert_true(player_a.is_dealer, "player_A is dealer in hand 1", results)
    
    # Check position-based stats
    analyzer = PreflopAnalyzer()
    stats_a = analyzer.analyze(hands, "player_A")
    
    assert_true(len(stats_a.hands_by_position) > 0, "position tracking has data", results)


def run_all_tests():
    """Run all test suites."""
    print("=" * 50)
    print("  POKER ANALYZER TEST SUITE")
    print("=" * 50)
    
    results = TestResults()
    
    test_models(results)
    test_parser(results)
    test_preflop_stats(results)
    test_postflop_stats(results)
    test_showdown_stats(results)
    test_aggregate_profile(results)
    test_edge_cases(results)
    test_position_tracking(results)
    
    success = results.summary()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
