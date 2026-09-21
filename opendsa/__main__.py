"""CLI entry: python -m opendsa [--new] [--model NAME] [--config PATH].

The TUI decides whether to show a Resume / Start screen; this module only
connects the DB, seeds the curriculum, and builds the model adapter.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Sequence

from . import db
from . import session
from .adapters import get_adapter
from .config import load_config
from .env import load_dotenv


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv()  # GOOGLE_API_KEY / GEMINI_MODEL may live in .env
    parser = argparse.ArgumentParser(prog="opendsa", description="DSA study guide (TUI)")
    parser.add_argument("--new", action="store_true", help="start a fresh session")
    parser.add_argument("--model", default=None, help="model name (overrides config)")
    parser.add_argument("--config", default=None, help="path to config.toml")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    model = os.environ.get("GEMINI_MODEL") or args.model or cfg.app.default_model
    conn = db.connect(cfg.app.database_path)
    session.seed(conn, cfg)
    adapter = get_adapter(cfg.model.provider, model)

    try:
        from .tui.app import StudyApp

        StudyApp(cfg=cfg, conn=conn, adapter=adapter, model=model, force_new=args.new).run()
    except KeyboardInterrupt:
        return 130
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))