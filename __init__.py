"""
Poker Analyzer - A comprehensive poker hand history analysis tool.

This package provides tools for parsing poker hand histories and
computing detailed statistics to profile player tendencies.

Main components:
- models: Core data structures (ParsedHand, PlayerAction, etc.)
- parser: Load and parse JSON hand histories
- stats: Statistical analysis modules (preflop, postflop, showdown)

Usage:
    from poker_analyzer import load_hands, generate_profile
    
    hands = load_hands("hands.json")
    profile = generate_profile(hands, "player_id")
    
    print(f"VPIP: {profile.preflop.vpip:.1%}")
    print(f"Style: {profile.play_style.value}")
"""

from models import (
    ActionType, Street, HandStrength,
    PlayerAction, PlayerInHand, HandResult, ParsedHand,
    parse_hand_strength
)

from parser import HandParser, load_hands

from stats import (
    PreflopStats, PostflopStats, ShowdownStats,
    PlayerProfile, PlayStyle, ConditionalRule, Exploit,
    calculate_preflop_stats, calculate_postflop_stats,
    calculate_showdown_stats, generate_profile
)


__version__ = "1.0.0"

__all__ = [
    # Models
    'ActionType',
    'Street', 
    'HandStrength',
    'PlayerAction',
    'PlayerInHand',
    'HandResult',
    'ParsedHand',
    'parse_hand_strength',
    
    # Parser
    'HandParser',
    'load_hands',
    
    # Stats
    'PreflopStats',
    'PostflopStats', 
    'ShowdownStats',
    'PlayerProfile',
    'PlayStyle',
    'ConditionalRule',
    'Exploit',
    'calculate_preflop_stats',
    'calculate_postflop_stats',
    'calculate_showdown_stats',
    'generate_profile',
]
