"""Keep static HTML and its CSS/JS release consistent across browser caches."""
import argparse
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "docs"
ASSETS = ("app.js", "styles.css", "explorer.css")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    updated = html
    for asset in ASSETS:
        version = hashlib.sha256((ROOT / asset).read_bytes()).hexdigest()[:12]
        pattern = r'((?:src|href)=")' + re.escape(asset) + r'(?:\?v=[a-f0-9]{12})?"'
        updated, count = re.subn(pattern, lambda m: m[1] + asset + "?v=" + version + '"', updated)
        if count != 1:
            raise ValueError(f"Expected one HTML reference for {asset}, got {count}")
    if args.check:
        if updated != html:
            parser.exit(1, "Static asset versions are stale. Run npm run build.\n")
        print("Static asset versions match CSS/JS contents.")
    else:
        (ROOT / "index.html").write_text(updated, encoding="utf-8")
        print("Updated CSS/JS content versions in docs/index.html.")


if __name__ == "__main__":
    main()
