#!/usr/bin/env python3
"""
Poker Analyzer - Command Line Interface

Analyze poker hand histories to profile player tendencies.

Usage:
    python main.py <player_name> [--output report.txt]
    python main.py charlie
    python main.py wyatt --json
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Optional, Dict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from parser import load_hands
from stats.aggregate import generate_profile, PlayerProfile


def load_player_mappings(csv_path: Path) -> Dict[str, str]:
    """Load player name to ID mappings from CSV file.

    CSV format:
        name1,name2,...
        id1,id2,...

    Returns:
        Dict mapping lowercase player names to IDs
    """
    mappings = {}

    try:
        with open(csv_path, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)

            if len(rows) >= 2:
                names = rows[0]
                ids = rows[1]

                for name, player_id in zip(names, ids):
                    if name and player_id:
                        mappings[name.strip().lower()] = player_id.strip()
    except FileNotFoundError:
        print(f"Warning: Player mapping file not found: {csv_path}", file=sys.stderr)
    except Exception as e:
        print(f"Warning: Error reading player mappings: {e}", file=sys.stderr)

    return mappings


def format_percentage(value: float, decimals: int = 1) -> str:
    """Format a 0-1 float as a percentage string."""
    return f"{value * 100:.{decimals}f}%"


def format_float(value: float, decimals: int = 2) -> str:
    """Format a float with specified decimals."""
    if value == float('inf'):
        return "∞"
    return f"{value:.{decimals}f}"


def print_divider(char: str = "─", width: int = 60):
    """Print a divider line."""
    print(char * width)


def print_section(title: str):
    """Print a section header."""
    print()
    print_divider("═")
    print(f"  {title}")
    print_divider("═")


def generate_text_report(profile: PlayerProfile, player_name: Optional[str] = None) -> str:
    """Generate a comprehensive text report for a player profile."""

    lines = []

    def add(text: str = ""):
        lines.append(text)

    def add_divider(char: str = "─", width: int = 60):
        lines.append(char * width)

    def add_section(title: str):
        add()
        add_divider("═")
        add(f"  {title}")
        add_divider("═")

    # Header
    add_divider("═")
    if player_name:
        add(f"  PLAYER PROFILE: {player_name}")
    else:
        add(f"  PLAYER PROFILE: {profile.player_id}")
    add_divider("═")
    add()
    add(f"Hands Analyzed: {profile.hands_analyzed}")
    add(f"Sample Confidence: {profile.sample_confidence}")
    add(f"Play Style: {profile.play_style.value}")
    
    # Preflop Stats
    add_section("PREFLOP STATISTICS")
    pf = profile.preflop
    
    add(f"VPIP:          {format_percentage(pf.vpip)} ({pf.vpip_count}/{pf.hands_played})")
    add(f"PFR:           {format_percentage(pf.pfr)} ({pf.pfr_count}/{pf.hands_played})")
    add(f"VPIP-PFR Gap:  {format_percentage(pf.vpip_pfr_gap)}")
    add()
    add(f"Limp Rate:     {format_percentage(pf.limp_rate)}")
    add(f"3-Bet %:       {format_percentage(pf.three_bet_frequency)} ({pf.three_bet_count}/{pf.three_bet_opportunities} opportunities)")
    add(f"Fold to 3-Bet: {format_percentage(pf.fold_to_3bet)} ({pf.fold_to_3bet_count}/{pf.fold_to_3bet_opportunities} opportunities)")
    
    if pf.open_raise_sizes:
        add(f"Avg Open Size: {format_float(pf.avg_open_raise_size)}x BB")
    
    # Position breakdown (if enough data)
    if pf.hands_by_position:
        add()
        add("By Position (0=BTN, 1=SB, 2=BB, 3+=EP/MP):")
        for pos in sorted(pf.hands_by_position.keys()):
            hands = pf.hands_by_position[pos]
            vpip_pct = format_percentage(pf.vpip_at_position(pos))
            pfr_pct = format_percentage(pf.pfr_at_position(pos))
            add(f"  Pos {pos}: VPIP {vpip_pct}, PFR {pfr_pct} ({hands} hands)")
    
    # Postflop Stats
    add_section("POSTFLOP STATISTICS")
    post = profile.postflop
    
    add(f"Aggression Factor:    {format_float(post.total_aggression_factor)}")
    add(f"Aggression Frequency: {format_percentage(post.total_aggression_frequency)}")
    add()
    
    # By street
    add("FLOP:")
    add(f"  C-Bet %:        {format_percentage(post.flop.cbet_frequency)} ({post.flop.cbets_made}/{post.flop.cbet_opportunities})")
    add(f"  Fold to Bet:    {format_percentage(post.flop.fold_to_bet)} ({post.flop.fold_to_bet_count}/{post.flop.faced_bet_count})")
    add(f"  Aggression Freq: {format_percentage(post.flop.aggression_frequency)}")
    if post.flop.bet_sizes:
        add(f"  Avg Bet Size:   {format_percentage(post.flop.avg_bet_size)} pot")
    
    add()
    add("TURN:")
    add(f"  C-Bet %:        {format_percentage(post.turn.cbet_frequency)} ({post.turn.cbets_made}/{post.turn.cbet_opportunities})")
    add(f"  Double Barrel:  {format_percentage(post.double_barrel_frequency)} ({post.double_barrels}/{post.double_barrel_opportunities})")
    add(f"  Fold to Bet:    {format_percentage(post.turn.fold_to_bet)}")
    add(f"  Aggression Freq: {format_percentage(post.turn.aggression_frequency)}")
    if post.turn.bet_sizes:
        add(f"  Avg Bet Size:   {format_percentage(post.turn.avg_bet_size)} pot")
    
    add()
    add("RIVER:")
    add(f"  C-Bet %:        {format_percentage(post.river.cbet_frequency)} ({post.river.cbets_made}/{post.river.cbet_opportunities})")
    add(f"  Triple Barrel:  {format_percentage(post.triple_barrel_frequency)} ({post.triple_barrels}/{post.triple_barrel_opportunities})")
    add(f"  Fold to Bet:    {format_percentage(post.river.fold_to_bet)}")
    add(f"  Aggression Freq: {format_percentage(post.river.aggression_frequency)}")
    if post.river.bet_sizes:
        add(f"  Avg Bet Size:   {format_percentage(post.river.avg_bet_size)} pot")
    
    add()
    add(f"Check-Raise %:    {format_percentage(post.check_raise_frequency)} ({post.check_raises}/{post.check_raise_opportunities})")
    add(f"Overbet %:        {format_percentage(post.overbet_frequency)} ({post.overbet_count}/{post.total_bets} bets)")
    
    # Showdown Stats
    add_section("SHOWDOWN STATISTICS")
    sd = profile.showdown
    
    add(f"WTSD (overall):   {format_percentage(sd.wtsd)} ({sd.saw_showdown}/{sd.hands_played})")
    add(f"WTSD (saw flop):  {format_percentage(sd.wtsd_flop)} ({sd.wtsd_after_flop}/{sd.saw_flop})")
    add(f"W$SD:             {format_percentage(sd.w_sd)} ({sd.won_at_showdown}/{sd.saw_showdown})")
    add()
    
    if sd.showdown_strengths:
        add(f"Avg Showdown Strength: {format_float(sd.avg_showdown_strength)} (1=high card, 6=flush)")
        add(f"Avg Winning Strength:  {format_float(sd.avg_winning_strength)}")
        add(f"Avg Losing Strength:   {format_float(sd.avg_losing_strength)}")
    
    if sd.river_bet_strength_samples:
        add()
        add(f"River Bets to Showdown: {sd.river_bets_to_showdown}")
        add(f"River Bet Value Rate:   {format_percentage(sd.river_bet_value_rate)} (trips+)")
        add(f"River Bet Bluff Rate:   {format_percentage(sd.river_bet_bluff_rate)} (pair or worse)")
    
    # Bet-Strength Correlation
    river_analysis = sd.bet_strength_correlation.get_street_analysis("river")
    if river_analysis:
        add()
        add("Bet Size → Hand Strength (River):")
        for bucket in ["tiny", "small", "medium", "large", "overbet"]:
            if bucket in river_analysis:
                data = river_analysis[bucket]
                add(f"  {bucket.capitalize():8} ({data['samples']:2} samples): "
                    f"Avg Strength {format_float(data['avg_strength'])}, "
                    f"Value {format_percentage(data['value_rate'])}, "
                    f"Bluff {format_percentage(data['bluff_rate'])}")
    
    # Tendencies
    if profile.tendencies:
        add_section("IDENTIFIED TENDENCIES")
        for tendency in profile.tendencies:
            add(f"• {tendency}")
    
    # Conditional Rules
    if profile.conditional_rules:
        add_section("CONDITIONAL RULES")
        for rule in profile.conditional_rules:
            add(f"• {rule}")
    
    # Exploits
    if profile.exploits:
        add_section("EXPLOITS & COUNTER-STRATEGIES")
        for exploit in profile.exploits:
            add(f"[{exploit.category.upper()}] {exploit.description}")
            add(f"  → {exploit.counter_strategy}")
            add()
    
    # Footer
    add_divider("═")
    add(f"  Analysis complete. Confidence: {profile.sample_confidence}")
    add_divider("═")
    
    return "\n".join(lines)


def generate_json_report(profile: PlayerProfile) -> dict:
    """Generate a JSON-serializable report dictionary."""
    
    pf = profile.preflop
    post = profile.postflop
    sd = profile.showdown
    
    return {
        "player_id": profile.player_id,
        "hands_analyzed": profile.hands_analyzed,
        "sample_confidence": profile.sample_confidence,
        "play_style": profile.play_style.value,
        
        "preflop": {
            "vpip": round(pf.vpip, 4),
            "pfr": round(pf.pfr, 4),
            "vpip_pfr_gap": round(pf.vpip_pfr_gap, 4),
            "limp_rate": round(pf.limp_rate, 4),
            "three_bet_frequency": round(pf.three_bet_frequency, 4),
            "fold_to_3bet": round(pf.fold_to_3bet, 4),
            "avg_open_raise_size": round(pf.avg_open_raise_size, 2),
            "hands_played": pf.hands_played,
        },
        
        "postflop": {
            "aggression_factor": round(post.total_aggression_factor, 2) if post.total_aggression_factor != float('inf') else None,
            "aggression_frequency": round(post.total_aggression_frequency, 4),
            "flop": {
                "cbet": round(post.flop.cbet_frequency, 4),
                "fold_to_bet": round(post.flop.fold_to_bet, 4),
                "avg_bet_size": round(post.flop.avg_bet_size, 4),
            },
            "turn": {
                "cbet": round(post.turn.cbet_frequency, 4),
                "double_barrel": round(post.double_barrel_frequency, 4),
                "fold_to_bet": round(post.turn.fold_to_bet, 4),
            },
            "river": {
                "cbet": round(post.river.cbet_frequency, 4),
                "triple_barrel": round(post.triple_barrel_frequency, 4),
                "fold_to_bet": round(post.river.fold_to_bet, 4),
            },
            "check_raise_frequency": round(post.check_raise_frequency, 4),
            "overbet_frequency": round(post.overbet_frequency, 4),
        },
        
        "showdown": {
            "wtsd": round(sd.wtsd, 4),
            "w_sd": round(sd.w_sd, 4),
            "avg_showdown_strength": round(sd.avg_showdown_strength, 2),
            "river_bet_value_rate": round(sd.river_bet_value_rate, 4),
            "river_bet_bluff_rate": round(sd.river_bet_bluff_rate, 4),
        },
        
        "tendencies": profile.tendencies,
        
        "conditional_rules": [
            {
                "condition": r.condition,
                "conclusion": r.conclusion,
                "confidence": round(r.confidence, 4),
                "sample_size": r.sample_size
            }
            for r in profile.conditional_rules
        ],
        
        "exploits": [
            {
                "category": e.category,
                "description": e.description,
                "counter_strategy": e.counter_strategy,
                "confidence": round(e.confidence, 4)
            }
            for e in profile.exploits
        ]
    }


def main():
    """Main entry point for CLI."""

    parser = argparse.ArgumentParser(
        description="Analyze poker hand histories to profile player tendencies across all hand files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py charlie
  python main.py wyatt --json
  python main.py charlie --output report.txt
        """
    )

    parser.add_argument(
        "player_name",
        type=str,
        help="Name of the player to analyze (from names.csv)"
    )

    parser.add_argument(
        "--output", "-o",
        type=str,
        help="Output file path (default: print to stdout)"
    )

    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output in JSON format"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    parser.add_argument(
        "--hands-dir",
        type=str,
        default="hands",
        help="Directory containing hand history JSON files (default: hands)"
    )

    parser.add_argument(
        "--names-csv",
        type=str,
        default="names.csv",
        help="CSV file mapping player names to IDs (default: names.csv)"
    )

    args = parser.parse_args()

    # Set up paths
    script_dir = Path(__file__).parent
    hands_dir = script_dir / args.hands_dir
    names_csv = script_dir / args.names_csv

    # Load player name mappings
    player_mappings = load_player_mappings(names_csv)

    if args.verbose:
        print(f"Loaded {len(player_mappings)} player mappings", file=sys.stderr)

    # Look up player ID from name
    player_name_lower = args.player_name.lower()
    player_id = player_mappings.get(player_name_lower)

    if not player_id:
        print(f"Error: Player '{args.player_name}' not found in {names_csv}", file=sys.stderr)
        print(f"Available players: {', '.join(sorted(player_mappings.keys()))}", file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        print(f"Player '{args.player_name}' -> ID '{player_id}'", file=sys.stderr)

    # Find all hand files in the hands directory
    if not hands_dir.exists():
        print(f"Error: Hands directory not found: {hands_dir}", file=sys.stderr)
        sys.exit(1)

    hand_files = sorted(hands_dir.glob("*.json"))

    if not hand_files:
        print(f"Error: No JSON files found in {hands_dir}", file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        print(f"Found {len(hand_files)} hand history file(s)", file=sys.stderr)

    # Load and aggregate hands from all files
    all_hands = []
    for hand_file in hand_files:
        try:
            hands = load_hands(str(hand_file))
            all_hands.extend(hands)
            if args.verbose:
                print(f"  Loaded {len(hands)} hands from {hand_file.name}", file=sys.stderr)
        except FileNotFoundError:
            print(f"Warning: File not found: {hand_file}", file=sys.stderr)
            continue
        except json.JSONDecodeError as e:
            print(f"Warning: Invalid JSON in {hand_file}: {e}", file=sys.stderr)
            continue

    if not all_hands:
        print("Error: No hands loaded from any files", file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        print(f"Total hands loaded: {len(all_hands)}", file=sys.stderr)

    # Generate profile across all hands
    profile = generate_profile(all_hands, player_id)

    if profile.hands_analyzed == 0:
        print(f"Error: Player '{args.player_name}' (ID: {player_id}) not found in any hands", file=sys.stderr)
        sys.exit(1)

    # Generate report
    if args.json:
        report_data = generate_json_report(profile)
        report_data["player_name"] = args.player_name  # Add player name to JSON output
        report = json.dumps(report_data, indent=2)
    else:
        report = generate_text_report(profile, args.player_name)

    # Output
    if args.output:
        with open(args.output, 'w') as f:
            f.write(report)
        if args.verbose:
            print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(report)


if __name__ == "__main__":
    main()
