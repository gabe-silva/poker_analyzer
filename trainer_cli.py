#!/usr/bin/env python3
"""CLI utility for trainer scenario generation and progress stats."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from trainer.service import TrainerService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Trainer CLI")
    parser.add_argument(
        "--db",
        default="trainer/data/trainer.db",
        help="SQLite database path (default: trainer/data/trainer.db)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Generate one scenario from filters")
    gen.add_argument("--num-players", type=int, default=6)
    gen.add_argument("--street", default="flop", choices=["preflop", "flop", "turn", "river"])
    gen.add_argument(
        "--node-type",
        default="single_raised_pot",
        choices=["single_raised_pot", "three_bet_pot", "four_bet_pot"],
    )
    gen.add_argument(
        "--action-context",
        default="facing_bet_and_call",
        choices=["checked_to_hero", "facing_bet", "facing_bet_and_call"],
    )
    gen.add_argument("--hero-position", default="BTN")
    gen.add_argument("--players-in-hand", type=int, default=3)
    gen.add_argument("--default-stack-bb", type=float, default=100.0)
    stack_mode = gen.add_mutually_exclusive_group()
    stack_mode.add_argument("--equal-stacks", dest="equal_stacks", action="store_true", default=True)
    stack_mode.add_argument("--custom-stacks", dest="equal_stacks", action="store_false")
    gen.add_argument("--seed", type=int, default=None)
    gen.add_argument("--hero-vpip", type=float, default=30.0, help="Hero VPIP in percent")
    gen.add_argument("--hero-pfr", type=float, default=22.0, help="Hero PFR in percent")
    gen.add_argument("--hero-af", type=float, default=2.8, help="Hero aggression factor")
    gen.add_argument("--hero-3bet", type=float, default=9.0, help="Hero 3-bet in percent")
    gen.add_argument("--hero-fold-3bet", type=float, default=54.0, help="Hero fold-to-3bet in percent")
    gen.add_argument("--randomize-hero-profile", action="store_true", help="Randomize hero stats for each generated scenario")
    gen.add_argument("--randomize-archetypes", action="store_true", help="Randomize opponent archetypes for each generated scenario")

    sub.add_parser("progress", help="Show aggregate standings")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    service = TrainerService(db_path=Path(args.db))

    if args.command == "generate":
        payload = {
            "num_players": args.num_players,
            "street": args.street,
            "node_type": args.node_type,
            "action_context": args.action_context,
            "hero_position": args.hero_position,
            "players_in_hand": args.players_in_hand,
            "default_stack_bb": args.default_stack_bb,
            "equal_stacks": bool(args.equal_stacks),
            "hero_profile": {
                "vpip": args.hero_vpip,
                "pfr": args.hero_pfr,
                "af": args.hero_af,
                "three_bet": args.hero_3bet,
                "fold_to_3bet": args.hero_fold_3bet,
            },
            "randomize_hero_profile": bool(args.randomize_hero_profile),
            "randomize_archetypes": bool(args.randomize_archetypes),
        }
        if args.seed is not None:
            payload["seed"] = args.seed
        scenario = service.generate(payload)
        print(json.dumps(scenario, indent=2))
        return

    if args.command == "progress":
        print(json.dumps(service.progress(), indent=2))
        return

    raise RuntimeError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
