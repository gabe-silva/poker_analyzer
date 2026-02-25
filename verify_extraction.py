#!/usr/bin/env python3
"""
Verification script to ensure data extraction is working correctly.
Tests that different files produce different statistics.
"""

import hashlib
import json
from pathlib import Path
from parser import load_hands
from stats.aggregate import generate_profile

def verify_file_extraction(file_path: Path, player_id: str):
    """Load and analyze a single file, return detailed stats."""

    # Calculate file hash
    with open(file_path, 'rb') as f:
        file_hash = hashlib.md5(f.read()).hexdigest()

    # Load raw JSON to count hands
    with open(file_path, 'r') as f:
        data = json.load(f)
        raw_hand_count = len(data.get('hands', []))

    # Parse hands
    hands = load_hands(str(file_path))

    # Count hands with player
    hands_with_player = sum(1 for h in hands if h.get_player_by_id(player_id))

    # Generate profile
    profile = generate_profile(hands, player_id) if hands_with_player > 0 else None

    return {
        'file': file_path.name,
        'file_hash': file_hash,
        'raw_hand_count': raw_hand_count,
        'parsed_hand_count': len(hands),
        'hands_with_player': hands_with_player,
        'hands_analyzed': profile.hands_analyzed if profile else 0,
        'vpip': profile.preflop.vpip if profile else 0,
        'pfr': profile.preflop.pfr if profile else 0,
        'vpip_count': profile.preflop.vpip_count if profile else 0,
        'pfr_count': profile.preflop.pfr_count if profile else 0,
    }

def main():
    """Run verification on all hand files."""

    # Test with charlie's ID
    player_id = "VQtUzD0dy6"  # charlie
    player_name = "charlie"

    print(f"=" * 70)
    print(f"DATA EXTRACTION VERIFICATION")
    print(f"=" * 70)
    print(f"\nTesting extraction for player: {player_name} (ID: {player_id})\n")

    # Check all directories
    for directory in ['hands', 'hands_bank']:
        dir_path = Path(directory)

        if not dir_path.exists():
            print(f"Directory '{directory}' not found, skipping...")
            continue

        json_files = sorted(dir_path.glob('*.json'))

        if not json_files:
            print(f"No JSON files in '{directory}', skipping...")
            continue

        print(f"\n{'=' * 70}")
        print(f"DIRECTORY: {directory}/")
        print(f"{'=' * 70}\n")

        for json_file in json_files:
            print(f"File: {json_file.name}")
            print(f"-" * 70)

            stats = verify_file_extraction(json_file, player_id)

            print(f"  File Hash:          {stats['file_hash'][:16]}...")
            print(f"  Raw Hands in JSON:  {stats['raw_hand_count']}")
            print(f"  Parsed Hands:       {stats['parsed_hand_count']}")
            print(f"  Hands with Player:  {stats['hands_with_player']}")
            print(f"  Hands Analyzed:     {stats['hands_analyzed']}")

            if stats['hands_analyzed'] > 0:
                print(f"\n  Statistics:")
                print(f"    VPIP Count:       {stats['vpip_count']}/{stats['hands_analyzed']} ({stats['vpip']:.1%})")
                print(f"    PFR Count:        {stats['pfr_count']}/{stats['hands_analyzed']} ({stats['pfr']:.1%})")
            else:
                print(f"\n  No hands analyzed (player not in this file)")

            print()

    print(f"\n{'=' * 70}")
    print(f"VERIFICATION COMPLETE")
    print(f"{'=' * 70}\n")
    print("If files are truly different, the hashes and statistics should differ.")
    print("If you're seeing identical stats across different files, check:")
    print("  1. Are the files actually different? (check hashes)")
    print("  2. Clear Python cache: rm -rf __pycache__ stats/__pycache__")
    print("  3. Is the player in all the files being compared?")
    print()

if __name__ == "__main__":
    main()
