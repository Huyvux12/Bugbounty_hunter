from __future__ import annotations

import os
from pathlib import Path

from feed_bot.store import REPO_ROOT


def load_dotenv() -> list[str]:
    loaded = []
    for path in (REPO_ROOT / ".env", Path.cwd() / ".env"):
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = value
        loaded.append(str(path))
    return loaded
