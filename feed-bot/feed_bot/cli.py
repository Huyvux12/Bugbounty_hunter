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
    parser.add_argument(
        "--probe-hackenproof",
        action="store_true",
        help="Call HackenProof MCP read tools and print the raw shape",
    )
    args = parser.parse_args(argv)
    if args.probe_hackenproof:
        from feed_bot.probe_hackenproof import main as probe_main

        return probe_main()
    result = run(
        data_dir=args.data_dir or (REPO_ROOT / "data"),
        docs_dir=args.docs_dir or (REPO_ROOT / "docs"),
        send_telegram=not args.no_telegram,
    )
    out = {
        "count": result["count"],
        "source_status": result["source_status"],
        "telegram_sent": result["telegram_sent"],
    }
    if result.get("telegram_error"):
        out["telegram_error"] = result["telegram_error"]
    print(json.dumps(out, indent=2))
    failures = [s for s in result["source_status"] if not s.get("ok")]
    return 0 if len(failures) < len(result["source_status"]) else 1


if __name__ == "__main__":
    sys.exit(main())
