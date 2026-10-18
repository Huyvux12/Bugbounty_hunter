from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from feed_bot.env import load_dotenv
from feed_bot.pipeline import run
from feed_bot.store import REPO_ROOT


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Ingest public bug bounty programs")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--docs-dir", type=Path, default=None)
    parser.add_argument("--no-telegram", action="store_true")
    args = parser.parse_args(argv)
    result = run(
        data_dir=args.data_dir or (REPO_ROOT / "data"),
        docs_dir=args.docs_dir or (REPO_ROOT / "docs"),
        send_telegram=not args.no_telegram,
    )
    out = {
        "count": result["count"],
        "quality": result["quality"],
        "source_status": result["source_status"],
        "telegram_sent": result["telegram_sent"],
        "llm_used": result.get("llm_used", 0),
    }
    if result.get("telegram_error"):
        out["telegram_error"] = result["telegram_error"]
    print(json.dumps(out, indent=2))
    # Optional LLM enrichment does not fail the public feed job.
    failures = [s for s in result["source_status"]
                if s.get("platform") != "llm" and not s.get("ok")]
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
