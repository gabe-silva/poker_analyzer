#!/usr/bin/env python3
"""Run the production Flask app locally for smoke testing."""

from __future__ import annotations

import os

from trainer.webapp import create_app

app = create_app()


def main() -> None:
    host = str(os.getenv("TRAINER_HOST", "127.0.0.1")).strip()
    port = int(str(os.getenv("TRAINER_PORT", "8787")).strip())
    debug = str(os.getenv("TRAINER_ENV", "development")).strip().lower() != "production"
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
