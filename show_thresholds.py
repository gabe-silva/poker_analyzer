#!/usr/bin/env python3
"""
Display all classification thresholds used by the poker analyzer.

Usage:
    python show_thresholds.py
    python show_thresholds.py --category preflop
    python show_thresholds.py --category style
"""

import argparse
from stats.aggregate import ProfileAnalyzer
from stats.showdown import BET_SIZE_BUCKETS


def print_section(title: str):
    """Print a section header."""
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def show_all_thresholds():
    """Display all thresholds used by the analyzer."""

    analyzer = ProfileAnalyzer()

    print("\n" + "=" * 60)
    print("  POKER ANALYZER - CLASSIFICATION THRESHOLDS")
    print("=" * 60)

    # Play Style Classification
    print_section("PLAY STYLE CLASSIFICATION")
    print(f"  VPIP Tight Threshold:      < {analyzer.VPIP_TIGHT * 100:.0f}%")
    print(f"  VPIP Loose Threshold:      > {analyzer.VPIP_LOOSE * 100:.0f}%")
    print(f"  PFR Passive Threshold:     < {analyzer.PFR_PASSIVE * 100:.0f}%")
    print(f"  PFR Aggressive Threshold:  > {analyzer.PFR_AGGRESSIVE * 100:.0f}%")
    print()
    print("  Extreme Classifications:")
    print("    - Maniac: VPIP > 45% AND AF > 3.5")
    print("    - Nit: VPIP < 14% AND PFR < 10%")

    # Confidence Levels
    print_section("SAMPLE CONFIDENCE LEVELS")
    print(f"  Low Confidence:      < {analyzer.HANDS_LOW_CONFIDENCE} hands")
    print(f"  Medium Confidence:   {analyzer.HANDS_LOW_CONFIDENCE}-{analyzer.HANDS_MEDIUM_CONFIDENCE-1} hands")
    print(f"  High Confidence:     {analyzer.HANDS_MEDIUM_CONFIDENCE}-{analyzer.HANDS_HIGH_CONFIDENCE-1} hands")
    print(f"  Very High:           ≥ {analyzer.HANDS_HIGH_CONFIDENCE} hands")

    # Preflop Tendencies
    print_section("PREFLOP TENDENCY THRESHOLDS")
    print("  VPIP Classifications:")
    print("    - Very Loose:  > 33%")
    print("    - Very Tight:  < 17%")
    print()
    print("  VPIP-PFR Gap:")
    print("    - Large Gap:   > 10% (calls too much)")
    print()
    print("  Limp Rate:")
    print("    - Frequent:    > 8%")
    print()
    print("  3-Bet Frequency:")
    print("    - Aggressive:  > 10%")
    print("    - Rarely:      < 3% (≥20 opportunities)")
    print()
    print("  Fold to 3-Bet:")
    print("    - Exploitable: > 70% (≥15 opportunities)")

    # Postflop Tendencies
    print_section("POSTFLOP TENDENCY THRESHOLDS")
    print("  Aggression Factor:")
    print("    - Highly Aggressive: > 3.0")
    print("    - Passive:           < 1.2")
    print()
    print("  C-Bet Frequency:")
    print("    - Very Frequent: > 70%")
    print("    - Rarely:        < 45%")
    print()
    print("  Double Barrel:")
    print("    - Aggressive:    > 60%")
    print("    - Gives Up:      < 35%")
    print()
    print("  Overbet Frequency:")
    print("    - Frequent:      > 10%")
    print()
    print("  Check-Raise:")
    print("    - Frequent:      > 15% (≥15 opportunities)")
    print()
    print("  Fold to Bet:")
    print("    - Exploitable:   > 55% (≥20 opportunities)")

    # Showdown Tendencies
    print_section("SHOWDOWN TENDENCY THRESHOLDS")
    print("  WTSD (Went To ShowDown):")
    print("    - Sticky (High):     > 33%")
    print("    - Rarely:            < 22%")
    print()
    print("  W$SD (Won $ at ShowDown):")
    print("    - Selective (High):  > 54%")
    print("    - Overvalues (Low):  < 45%")
    print()
    print("  Combined Exploit:")
    print("    - Calling Station:   WTSD > 33% AND W$SD < 45%")

    # Bet Sizing
    print_section("BET SIZE CLASSIFICATIONS")
    for bucket_name, (low, high) in BET_SIZE_BUCKETS.items():
        if high == float('inf'):
            print(f"  {bucket_name.capitalize():10} > {int(low * 100)}% pot")
        else:
            print(f"  {bucket_name.capitalize():10} {int(low * 100)}-{int(high * 100)}% pot")

    # Hand Strength
    print_section("HAND STRENGTH SCALE")
    print("  1  = High Card")
    print("  2  = Pair")
    print("  3  = Two Pair")
    print("  4  = Three of a Kind (Trips/Set)")
    print("  5  = Straight")
    print("  6  = Flush")
    print("  7  = Full House")
    print("  8  = Four of a Kind")
    print("  9  = Straight Flush")
    print("  10 = Royal Flush")
    print()
    print("  Bluff:  Strength ≤ 2 (Pair or worse)")
    print("  Value:  Strength ≥ 3 (Two Pair or better)")

    # Exploits
    print_section("EXPLOIT DETECTION THRESHOLDS")
    print("  Preflop:")
    print("    - Fold to 3-Bet:    > 70% (≥15 opps) → 3-bet bluff more")
    print("    - Limp Rate:        > 12%            → Raise limps aggressively")
    print("    - VPIP-PFR Gap:     > 12%            → Value bet thinner")
    print()
    print("  Postflop:")
    print("    - High C-Bet:       > 70%            → Float wider")
    print("    - Fold to Bet:      > 55% (≥20)      → Bluff liberally")
    print("    - Low Dbl Barrel:   < 40% (≥20)      → Call flop, expect check")
    print("    - Check-Raise:      > 15% (≥15)      → Check back marginal")
    print()
    print("  River:")
    print("    - Value-Heavy:      > 70% (≥8)       → Overfold to bets")
    print("    - Bluff-Heavy:      > 35% (≥8)       → Call down lighter")
    print()
    print("  Showdown:")
    print("    - Calling Station:  WTSD>33% & W$SD<45% → Value bet more")

    print("\n" + "=" * 60)
    print("  See THRESHOLDS.md for complete documentation")
    print("=" * 60 + "\n")


def show_category(category: str):
    """Show thresholds for a specific category."""
    analyzer = ProfileAnalyzer()

    category = category.lower()

    if category in ['style', 'classification']:
        print_section("PLAY STYLE CLASSIFICATION")
        print(f"  VPIP Tight:     < {analyzer.VPIP_TIGHT * 100:.0f}%")
        print(f"  VPIP Loose:     > {analyzer.VPIP_LOOSE * 100:.0f}%")
        print(f"  PFR Passive:    < {analyzer.PFR_PASSIVE * 100:.0f}%")
        print(f"  PFR Aggressive: > {analyzer.PFR_AGGRESSIVE * 100:.0f}%")
        print(f"\n  Maniac: VPIP > 45% AND AF > 3.5")
        print(f"  Nit:    VPIP < 14% AND PFR < 10%")

    elif category == 'preflop':
        print_section("PREFLOP THRESHOLDS")
        print("  Very Loose VPIP:    > 33%")
        print("  Very Tight VPIP:    < 17%")
        print("  Large VPIP-PFR Gap: > 10%")
        print("  Frequent Limper:    > 8%")
        print("  Aggressive 3-Bet:   > 10%")
        print("  Rarely 3-Bets:      < 3%")
        print("  Fold to 3-Bet:      > 70%")

    elif category == 'postflop':
        print_section("POSTFLOP THRESHOLDS")
        print("  High Aggression:    AF > 3.0")
        print("  Low Aggression:     AF < 1.2")
        print("  High C-Bet:         > 70%")
        print("  Low C-Bet:          < 45%")
        print("  High Dbl Barrel:    > 60%")
        print("  Low Dbl Barrel:     < 35%")
        print("  Frequent Overbet:   > 10%")
        print("  Frequent Check-Raise: > 15%")

    elif category == 'showdown':
        print_section("SHOWDOWN THRESHOLDS")
        print("  High WTSD:     > 33%")
        print("  Low WTSD:      < 22%")
        print("  High W$SD:     > 54%")
        print("  Low W$SD:      < 45%")
        print("\n  River Value Rate: > 70%")
        print("  River Bluff Rate: > 35%")

    elif category in ['bet', 'sizing']:
        print_section("BET SIZE BUCKETS")
        for bucket_name, (low, high) in BET_SIZE_BUCKETS.items():
            if high == float('inf'):
                print(f"  {bucket_name.capitalize():10} > {int(low * 100)}% pot")
            else:
                print(f"  {bucket_name.capitalize():10} {int(low * 100)}-{int(high * 100)}% pot")

    else:
        print(f"Unknown category: {category}")
        print("Available categories: style, preflop, postflop, showdown, bet")
        return

    print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Display poker analyzer classification thresholds",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python show_thresholds.py
  python show_thresholds.py --category style
  python show_thresholds.py --category preflop
  python show_thresholds.py --category postflop
        """
    )

    parser.add_argument(
        "--category", "-c",
        type=str,
        help="Show only specific category (style, preflop, postflop, showdown, bet)"
    )

    args = parser.parse_args()

    if args.category:
        show_category(args.category)
    else:
        show_all_thresholds()


if __name__ == "__main__":
    main()
