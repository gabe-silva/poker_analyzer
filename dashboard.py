#!/usr/bin/env python3
"""
Poker Analyzer Dashboard - Compare Multiple Players

Usage:
    python dashboard.py charlie wyatt
    python dashboard.py charlie wyatt gabe --port 8080
    python dashboard.py charlie wyatt --output comparison.html
"""

import argparse
import csv
import json
import sys
import webbrowser
import hashlib
from pathlib import Path
from typing import Dict, List
from http.server import HTTPServer, SimpleHTTPRequestHandler
import threading

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from parser import load_hands
from stats.aggregate import generate_profile, PlayerProfile


def load_player_mappings(csv_path: Path) -> Dict[str, str]:
    """Load player name to ID mappings from CSV file."""
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


def generate_html_dashboard(profiles: List[tuple], player_names: List[str]) -> str:
    """Generate an HTML dashboard comparing multiple players."""

    # Extract profiles
    player_data = [(name, profile) for name, profile in profiles]

    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Poker Player Comparison Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: #333;
            padding: 20px;
            min-height: 100vh;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
        }

        header {
            text-align: center;
            color: white;
            margin-bottom: 30px;
        }

        h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }

        .subtitle {
            font-size: 1.1em;
            opacity: 0.9;
        }

        .comparison-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }

        .player-card {
            background: white;
            border-radius: 12px;
            padding: 25px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            transition: transform 0.2s, box-shadow 0.2s;
        }

        .player-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 8px 12px rgba(0,0,0,0.2);
        }

        .player-header {
            border-bottom: 3px solid #2a5298;
            padding-bottom: 15px;
            margin-bottom: 20px;
        }

        .player-name {
            font-size: 1.8em;
            font-weight: bold;
            color: #1e3c72;
            margin-bottom: 5px;
        }

        .player-style {
            display: inline-block;
            padding: 5px 12px;
            background: #2a5298;
            color: white;
            border-radius: 15px;
            font-size: 0.9em;
            margin-top: 5px;
        }

        .stat-section {
            margin-bottom: 25px;
        }

        .section-title {
            font-size: 1.1em;
            font-weight: bold;
            color: #2a5298;
            margin-bottom: 12px;
            padding-bottom: 5px;
            border-bottom: 2px solid #e0e0e0;
        }

        .stat-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #f0f0f0;
        }

        .stat-row:last-child {
            border-bottom: none;
        }

        .stat-label {
            color: #666;
            font-weight: 500;
        }

        .stat-value {
            font-weight: bold;
            color: #1e3c72;
        }

        .stat-value.high {
            color: #d32f2f;
        }

        .stat-value.low {
            color: #388e3c;
        }

        .confidence {
            text-align: center;
            padding: 10px;
            background: #f5f5f5;
            border-radius: 6px;
            margin-top: 15px;
            font-size: 0.9em;
        }

        .tendency-list {
            list-style: none;
            padding-left: 0;
        }

        .tendency-list li {
            padding: 6px 0;
            padding-left: 20px;
            position: relative;
            color: #555;
            line-height: 1.4;
        }

        .tendency-list li:before {
            content: "▸";
            position: absolute;
            left: 0;
            color: #2a5298;
            font-weight: bold;
        }

        .exploit-item {
            background: #fff3cd;
            border-left: 4px solid #ff9800;
            padding: 12px;
            margin-bottom: 10px;
            border-radius: 4px;
        }

        .exploit-category {
            font-weight: bold;
            color: #e65100;
            font-size: 0.85em;
            text-transform: uppercase;
        }

        .exploit-description {
            margin: 5px 0;
            color: #333;
        }

        .exploit-counter {
            color: #666;
            font-size: 0.9em;
            font-style: italic;
        }

        .comparison-table {
            background: white;
            border-radius: 12px;
            padding: 25px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            overflow-x: auto;
            margin-top: 30px;
        }

        table {
            width: 100%;
            border-collapse: collapse;
        }

        th {
            background: #2a5298;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }

        td {
            padding: 10px 12px;
            border-bottom: 1px solid #e0e0e0;
        }

        tr:hover {
            background: #f5f5f5;
        }

        .metric-name {
            font-weight: 500;
            color: #555;
        }

        @media (max-width: 768px) {
            .comparison-grid {
                grid-template-columns: 1fr;
            }

            h1 {
                font-size: 1.8em;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>♠♥ Poker Player Comparison Dashboard ♣♦</h1>
            <p class="subtitle">Comprehensive Analysis & Head-to-Head Comparison</p>
        </header>

        <div class="comparison-grid">
"""

    # Generate individual player cards
    for player_name, profile in player_data:
        pf = profile.preflop
        post = profile.postflop
        sd = profile.showdown

        html += f"""
            <div class="player-card">
                <div class="player-header">
                    <div class="player-name">{player_name.upper()}</div>
                    <span class="player-style">{profile.play_style.value}</span>
                    <div class="confidence">
                        {profile.hands_analyzed} hands | {profile.sample_confidence} confidence
                    </div>
                </div>

                <div class="stat-section">
                    <div class="section-title">Preflop</div>
                    <div class="stat-row">
                        <span class="stat-label">VPIP</span>
                        <span class="stat-value">{format_percentage(pf.vpip)}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">PFR</span>
                        <span class="stat-value">{format_percentage(pf.pfr)}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">3-Bet</span>
                        <span class="stat-value">{format_percentage(pf.three_bet_frequency)}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Fold to 3-Bet</span>
                        <span class="stat-value">{format_percentage(pf.fold_to_3bet)}</span>
                    </div>
                </div>

                <div class="stat-section">
                    <div class="section-title">Postflop</div>
                    <div class="stat-row">
                        <span class="stat-label">Aggression Factor</span>
                        <span class="stat-value">{format_float(post.total_aggression_factor)}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Flop C-Bet</span>
                        <span class="stat-value">{format_percentage(post.flop.cbet_frequency)}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Turn C-Bet</span>
                        <span class="stat-value">{format_percentage(post.turn.cbet_frequency)}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">River C-Bet</span>
                        <span class="stat-value">{format_percentage(post.river.cbet_frequency)}</span>
                    </div>
                </div>

                <div class="stat-section">
                    <div class="section-title">Showdown</div>
                    <div class="stat-row">
                        <span class="stat-label">WTSD</span>
                        <span class="stat-value">{format_percentage(sd.wtsd)}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">W$SD</span>
                        <span class="stat-value">{format_percentage(sd.w_sd)}</span>
                    </div>
                </div>

                <div class="stat-section">
                    <div class="section-title">Key Tendencies</div>
                    <ul class="tendency-list">
"""

        for tendency in profile.tendencies[:5]:  # Show top 5
            html += f"                        <li>{tendency}</li>\n"

        html += """                    </ul>
                </div>
"""

        if profile.exploits:
            html += """                <div class="stat-section">
                    <div class="section-title">Exploits</div>
"""
            for exploit in profile.exploits[:3]:  # Show top 3
                html += f"""                    <div class="exploit-item">
                        <div class="exploit-category">[{exploit.category}]</div>
                        <div class="exploit-description">{exploit.description}</div>
                        <div class="exploit-counter">→ {exploit.counter_strategy}</div>
                    </div>
"""
            html += """                </div>
"""

        html += """            </div>
"""

    html += """        </div>

        <div class="comparison-table">
            <h2 style="margin-bottom: 20px; color: #1e3c72;">Side-by-Side Comparison</h2>
            <table>
                <thead>
                    <tr>
                        <th>Metric</th>
"""

    for player_name, _ in player_data:
        html += f"                        <th>{player_name.upper()}</th>\n"

    html += """                    </tr>
                </thead>
                <tbody>
"""

    # Comparison metrics
    metrics = [
        ("Hands Analyzed", lambda p: str(p.hands_analyzed)),
        ("Play Style", lambda p: p.play_style.value),
        ("VPIP", lambda p: format_percentage(p.preflop.vpip)),
        ("PFR", lambda p: format_percentage(p.preflop.pfr)),
        ("VPIP-PFR Gap", lambda p: format_percentage(p.preflop.vpip_pfr_gap)),
        ("3-Bet %", lambda p: format_percentage(p.preflop.three_bet_frequency)),
        ("Fold to 3-Bet", lambda p: format_percentage(p.preflop.fold_to_3bet)),
        ("Limp Rate", lambda p: format_percentage(p.preflop.limp_rate)),
        ("Aggression Factor", lambda p: format_float(p.postflop.total_aggression_factor)),
        ("Aggression Freq", lambda p: format_percentage(p.postflop.total_aggression_frequency)),
        ("Flop C-Bet", lambda p: format_percentage(p.postflop.flop.cbet_frequency)),
        ("Turn C-Bet", lambda p: format_percentage(p.postflop.turn.cbet_frequency)),
        ("River C-Bet", lambda p: format_percentage(p.postflop.river.cbet_frequency)),
        ("Double Barrel", lambda p: format_percentage(p.postflop.double_barrel_frequency)),
        ("Triple Barrel", lambda p: format_percentage(p.postflop.triple_barrel_frequency)),
        ("Check-Raise %", lambda p: format_percentage(p.postflop.check_raise_frequency)),
        ("WTSD", lambda p: format_percentage(p.showdown.wtsd)),
        ("W$SD", lambda p: format_percentage(p.showdown.w_sd)),
    ]

    for metric_name, metric_func in metrics:
        html += f"""                    <tr>
                        <td class="metric-name">{metric_name}</td>
"""
        for _, profile in player_data:
            value = metric_func(profile)
            html += f"""                        <td>{value}</td>
"""
        html += """                    </tr>
"""

    html += """                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""

    return html


def main():
    """Main entry point for dashboard."""

    parser = argparse.ArgumentParser(
        description="Compare multiple poker players in a dashboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python dashboard.py charlie wyatt
  python dashboard.py charlie wyatt gabe
  python dashboard.py charlie wyatt --output comparison.html --no-browser
  python dashboard.py charlie wyatt --port 8080
        """
    )

    parser.add_argument(
        "player_names",
        nargs='+',
        help="Names of players to compare (space-separated)"
    )

    parser.add_argument(
        "--output", "-o",
        type=str,
        help="Save HTML to file (default: dashboard.html)"
    )

    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't automatically open browser"
    )

    parser.add_argument(
        "--port", "-p",
        type=int,
        default=8000,
        help="Port for local server (default: 8000)"
    )

    parser.add_argument(
        "--hands-dir",
        type=str,
        default="hands",
        help="Directory containing hand history JSON files"
    )

    parser.add_argument(
        "--names-csv",
        type=str,
        default="names.csv",
        help="CSV file mapping player names to IDs"
    )

    args = parser.parse_args()

    # Set up paths
    script_dir = Path(__file__).parent
    hands_dir = script_dir / args.hands_dir
    names_csv = script_dir / args.names_csv

    # Load player mappings
    player_mappings = load_player_mappings(names_csv)

    if not player_mappings:
        print(f"Error: No player mappings found in {names_csv}", file=sys.stderr)
        sys.exit(1)

    # Validate player names
    player_ids = {}
    for name in args.player_names:
        name_lower = name.lower()
        player_id = player_mappings.get(name_lower)
        if not player_id:
            print(f"Error: Player '{name}' not found in {names_csv}", file=sys.stderr)
            print(f"Available players: {', '.join(sorted(player_mappings.keys()))}", file=sys.stderr)
            sys.exit(1)
        player_ids[name] = player_id

    print(f"Comparing {len(args.player_names)} players: {', '.join(args.player_names)}")

    # Load all hand files
    if not hands_dir.exists():
        print(f"Error: Hands directory not found: {hands_dir}", file=sys.stderr)
        sys.exit(1)

    hand_files = sorted(hands_dir.glob("*.json"))
    if not hand_files:
        print(f"Error: No JSON files found in {hands_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading {len(hand_files)} hand file(s)...")
    print("File fingerprints (to verify different files):")

    all_hands = []
    for hand_file in hand_files:
        try:
            # Calculate file hash to verify it's being read
            with open(hand_file, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()[:8]

            hands = load_hands(str(hand_file))
            print(f"  {hand_file.name}")
            print(f"    Hash: {file_hash}")
            print(f"    Hands: {len(hands)}")

            all_hands.extend(hands)
        except Exception as e:
            print(f"Warning: Error loading {hand_file.name}: {e}", file=sys.stderr)

    if not all_hands:
        print("Error: No hands loaded", file=sys.stderr)
        sys.exit(1)

    print(f"\nLoaded {len(all_hands)} total hands from all files")

    # Generate profiles for all players
    print(f"\nGenerating profiles...")
    profiles = []
    for name in args.player_names:
        player_id = player_ids[name]
        print(f"  Analyzing player '{name}' (ID: {player_id})...")

        # Count how many hands this player appears in
        hands_with_player = sum(1 for h in all_hands if h.get_player_by_id(player_id))
        print(f"    Found in {hands_with_player} hands")

        profile = generate_profile(all_hands, player_id)

        if profile.hands_analyzed == 0:
            print(f"    WARNING: No hands analyzed for {name}!", file=sys.stderr)
            continue

        profiles.append((name, profile))
        print(f"    ✓ Analyzed {profile.hands_analyzed} hands")
        print(f"    VPIP: {profile.preflop.vpip:.1%}, PFR: {profile.preflop.pfr:.1%}")

    if not profiles:
        print("Error: No valid profiles generated", file=sys.stderr)
        sys.exit(1)

    # Generate HTML dashboard
    html = generate_html_dashboard(profiles, args.player_names)

    # Save to file
    output_file = args.output if args.output else "dashboard.html"
    output_path = script_dir / output_file

    with open(output_path, 'w') as f:
        f.write(html)

    print(f"\nDashboard saved to: {output_path}")

    # Open in browser
    if not args.no_browser:
        print(f"Opening browser...")
        webbrowser.open(f'file://{output_path.absolute()}')

    print("\nDashboard ready!")


if __name__ == "__main__":
    main()
