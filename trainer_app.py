#!/usr/bin/env python3
"""Run the LAG cash-game trainer web app."""

from __future__ import annotations

import argparse
from pathlib import Path

from trainer.server import run_server
from trainer.service import TrainerService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start the LAG cash trainer UI and API server.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8787, help="Bind port (default: 8787)")
    parser.add_argument(
        "--db",
        default="trainer/data/trainer.db",
        help="SQLite database path (default: trainer/data/trainer.db)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not automatically open browser",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    service = TrainerService(db_path=Path(args.db))
    run_server(
        service=service,
        host=args.host,
        port=args.port,
        open_browser=not args.no_browser,
    )


if __name__ == "__main__":
    main()
