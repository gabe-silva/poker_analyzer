# Poker Analyzer

A comprehensive poker hand history analyzer that profiles player tendencies and identifies exploitable patterns.

## Features

- **Preflop Analysis**: VPIP, PFR, 3-bet frequency, fold to 3-bet, position-aware stats
- **Postflop Analysis**: C-bet frequency, aggression factor, bet sizing, barreling patterns
- **Showdown Analysis**: WTSD, W$SD, hand strength correlation with bet sizes
- **Player Profiling**: Automatic style classification (TAG, LAG, etc.)
- **Exploit Detection**: Actionable counter-strategies based on identified leaks
- **Interactive Dashboard**: Compare multiple players side-by-side in a visual dashboard
- **Multiple Output Formats**: Text report, JSON, or HTML dashboard

## Classification Thresholds

All classification assumptions and thresholds are documented in [THRESHOLDS.md](THRESHOLDS.md). This includes:
- Play style classifications (TAG, LAG, etc.)
- VPIP/PFR ranges for tight/loose and passive/aggressive
- Exploit detection thresholds
- Bet sizing buckets
- Sample size requirements
- All counter-strategy triggers

See the [full thresholds document](THRESHOLDS.md) to understand how the analyzer classifies player behavior.

You can also view thresholds interactively:
```bash
# Display all thresholds
python show_thresholds.py

# Show specific category
python show_thresholds.py --category preflop
python show_thresholds.py --category postflop
python show_thresholds.py --category style
```

## Installation

No external dependencies required for core functionality. Python 3.9+ recommended.

```bash
# Clone or download the poker_analyzer directory
cd poker_analyzer

# Run tests to verify installation
python test_analyzer.py
```

## Hosted Paid Web App (PythonAnywhere)

Production deployment with Stripe subscriptions and email-code login is now available.

- WSGI entrypoint: `wsgi.py`
- Production app runner: `trainer_webapp.py`
- Production dependencies: `requirements/production.txt`
- Full deployment guide: `DEPLOYMENT_PYTHONANYWHERE.md`

Local smoke test for the hosted app:

```bash
pip install -r requirements/production.txt
python trainer_webapp.py
```

### Optional Dependencies

For equity calculations and range analysis:

```bash
pip install eval7
```

## Usage

### Setup

First, create a `names.csv` file mapping player names to their IDs:

```csv
charlie,wyatt,alice
VQtUzD0dy6,U1ILe64ZWz,abcd1234ef
```

Place all your hand history JSON files in the `hands/` folder. The analyzer will automatically aggregate stats across all files.

### Command Line

```bash
# Basic usage - text report to stdout (analyzes all hand files)
python main.py charlie

# Output to file
python main.py charlie --output report.txt

# JSON output
python main.py wyatt --json

# JSON to file
python main.py alice --json --output report.json

# Verbose mode to see file loading details
python main.py charlie --verbose

# Custom paths
python main.py charlie --hands-dir my_hands --names-csv my_names.csv
```

### Dashboard - Compare Multiple Players

The dashboard provides a visual, side-by-side comparison of multiple players:

```bash
# Compare 2 players (opens in browser automatically)
python dashboard.py charlie wyatt

# Compare 3+ players
python dashboard.py charlie wyatt gabe

# Save to custom file
python dashboard.py charlie wyatt --output comparison.html

# Don't auto-open browser
python dashboard.py charlie wyatt --no-browser

# All options
python dashboard.py charlie wyatt gabe --output my_dashboard.html --no-browser
```

The dashboard includes:
- Individual player cards with key stats and tendencies
- Side-by-side comparison table
- Visual styling with color-coded metrics
- Exploit detection and counter-strategies
- Responsive design for mobile/desktop

### As a Library

```python
from poker_analyzer import load_hands, generate_profile

# Load hand history
hands = load_hands("hands.json")

# Generate profile
profile = generate_profile(hands, "target_player_id")

# Access statistics
print(f"VPIP: {profile.preflop.vpip:.1%}")
print(f"PFR: {profile.preflop.pfr:.1%}")
print(f"Aggression Factor: {profile.postflop.total_aggression_factor:.2f}")
print(f"Style: {profile.play_style.value}")

# View identified exploits
for exploit in profile.exploits:
    print(f"{exploit.description} → {exploit.counter_strategy}")
```

## Hand History Format

The analyzer expects JSON files with this structure:

```json
{
  "hands": [
    {
      "id": "hand_001",
      "dealerSeat": 0,
      "players": [
        {"id": "player_A", "seat": 0, "stack": 1000, "cards": ["Ah", "Kd"]},
        {"id": "player_B", "seat": 1, "stack": 850}
      ],
      "events": [
        {"payload": {"type": 3, "seat": 0, "amount": 5}},
        {"payload": {"type": 2, "seat": 1, "amount": 10}},
        ...
      ]
    }
  ]
}
```

### Action Type Codes

| Code | Action |
|------|--------|
| 0 | Check |
| 2 | Big Blind (forced) |
| 3 | Small Blind (forced) |
| 7 | Call |
| 8 | Bet / Raise |
| 9 | Board Dealt |
| 10 | Pot Awarded |
| 11 | Fold |

### Card Format

Cards can be specified as:
- String: `"Ah"`, `"Kd"`, `"Tc"` (rank + suit)
- Array: `["Ah", "Kd"]`

## Statistics Explained

### Preflop Stats

| Stat | Meaning | Good Range |
|------|---------|------------|
| **VPIP** | Voluntarily Put $ In Pot | 18-28% (tight) to 30-40% (loose) |
| **PFR** | Preflop Raise % | 15-22% (typical TAG) |
| **VPIP-PFR Gap** | Calling tendency | <8% good, >15% too passive |
| **3-Bet %** | Re-raise frequency | 6-10% value-heavy, >12% aggressive |
| **Fold to 3-Bet** | Defense vs 3-bet | <50% sticky, >65% exploitable |

### Postflop Stats

| Stat | Meaning | Good Range |
|------|---------|------------|
| **C-Bet %** | Continuation bet | 50-70% balanced, >75% too wide |
| **Aggression Factor** | (Bets+Raises)/Calls | 1.5-3.0 aggressive, <1.0 passive |
| **Double Barrel %** | Bet flop→turn | 40-60% balanced |
| **Fold to Bet** | How often folds facing bet | >50% exploitable |

### Showdown Stats

| Stat | Meaning | Good Range |
|------|---------|------------|
| **WTSD** | Went to Showdown % | 22-28% balanced |
| **W$SD** | Won $ at Showdown % | 50-55% good |
| **River Value Rate** | Strong hands when betting river | 60-80% balanced |

## Sample Output

```
════════════════════════════════════════════════════════════
  PLAYER PROFILE: oFoiuzFaF0
════════════════════════════════════════════════════════════

Hands Analyzed: 150
Sample Confidence: Medium
Play Style: Loose-Aggressive (LAG)

════════════════════════════════════════════════════════════
  PREFLOP STATISTICS
════════════════════════════════════════════════════════════
VPIP:          38.5% (58/150)
PFR:           28.0% (42/150)
VPIP-PFR Gap:  10.5%

Limp Rate:     2.0%
3-Bet %:       12.3% (8/65 opportunities)
Fold to 3-Bet: 55.0% (11/20 opportunities)

════════════════════════════════════════════════════════════
  IDENTIFIED TENDENCIES
════════════════════════════════════════════════════════════
• Plays very loose preflop (VPIP > 35%)
• Aggressive 3-bettor
• C-bets very frequently (easy to float)
• Barrels aggressively on turn

════════════════════════════════════════════════════════════
  EXPLOITS & COUNTER-STRATEGIES
════════════════════════════════════════════════════════════
[POSTFLOP] C-bets 78% of flops
  → Float flops wider, raise bluff occasionally

[RIVER] River bets are 82% value
  → Overfold river to their bets
```

## Confidence Levels

| Hands | Confidence | What You Can Trust |
|-------|------------|--------------------|
| <50 | Low | Basic tendencies only |
| 50-150 | Medium | Preflop stats, aggression |
| 150-500 | High | Most stats reliable |
| >500 | Very High | All stats, bet sizing tells |

## Project Structure

```
poker_analyzer/
├── __init__.py          # Package exports
├── models.py            # Core data structures
├── parser.py            # JSON hand history parser
├── main.py              # CLI entry point
├── test_analyzer.py     # Test suite
├── sample_hands.json    # Example data
├── stats/
│   ├── __init__.py
│   ├── preflop.py       # Preflop statistics
│   ├── postflop.py      # Postflop statistics
│   ├── showdown.py      # Showdown statistics
│   └── aggregate.py     # Profile generation
└── README.md
```

## Extending the Analyzer

### Adding New Statistics

1. Add the stat to the appropriate `Stats` dataclass in `stats/`
2. Update the analyzer class to compute it
3. Add it to the report generator in `main.py`

### Custom Hand Formats

Subclass `HandParser` and override `_parse_events()` to handle different formats:

```python
class MyParser(HandParser):
    def _parse_events(self, events, seat_to_player, hand_id):
        # Custom parsing logic
        ...
```

## LAG Cash Trainer (Scenario Practice + EV Feedback)

A dedicated trainer is now included for focused cash-game drills with position, archetype, and stack control.
Each submitted decision now returns:
- EV table for all legal lines
- Leak decomposition (factor-by-factor EV loss attribution)
- Hero-profile-aware feedback using VPIP/PFR/AF + 3-bet tendencies
- Position plan guidance tied to your profile
- Spot math diagnostics (pot-odds equity threshold, MDF, SPR banding, bluff risk/reward)
- Opponent-mix-targeted exploit notes (calling stations, overfolders, aggressive regs, trappy pools)

### Start the Trainer UI

```bash
python trainer_app.py
```

Pages:
- Setup: `http://127.0.0.1:8787/setup.html`
- Trainer: `http://127.0.0.1:8787/trainer.html`
- Play vs Profile: `http://127.0.0.1:8787/play.html`
- Standings: `http://127.0.0.1:8787/standings.html`

Navigation behavior:
- Setup values persist when moving between pages (same browser/local storage).
- On Trainer, `New Setup` generates a new scenario using your saved setup config without leaving the page.
- On Play, you can run full hands vs preset/analyzer/custom opponents and optionally start from a targeted scenario.
- Play mode now uses stat-derived villain ranges that update by street (preflop/flop/turn/river) with profile-based range adherence/deviation.
- Play mode also adapts to hero image (your observed aggression, raise pressure, and bluff declarations), not just static opponent ranges.
- On Standings, `Clear Saved Hands` wipes saved scenarios and attempts.

New setup toggles:
- Randomize Hero Stats each scenario (VPIP/PFR/AF/3-bet/fold-to-3bet)
- Randomize Opponent Archetypes each scenario

Optional flags:

```bash
python trainer_app.py --host 127.0.0.1 --port 8787 --db trainer/data/trainer.db --no-browser
```

### CLI Scenario Generation

```bash
# Generate one spot with filters
python trainer_cli.py generate --num-players 6 --street flop --hero-position BTN --players-in-hand 3

# Same, but randomize hero profile and opponent archetypes
python trainer_cli.py generate --num-players 6 --street flop --hero-position BTN --players-in-hand 3 --randomize-hero-profile --randomize-archetypes

# View standings/progress
python trainer_cli.py progress
```

Structured study plan:
- `trainer/LAG_STUDY_CURRICULUM.md`

## Known Limitations

- Does not track timing tells
- No tournament-specific adjustments (ICM, bubble, etc.)
- Ante games not fully supported
- Multi-way pots may affect some postflop stats

## License

MIT License - Use freely for personal or commercial projects.

## Acknowledgments

Inspired by tracking software like PokerTracker and Hold'em Manager, designed for
lightweight use without database overhead.
