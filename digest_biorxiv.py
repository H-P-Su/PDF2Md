"""CLI script to generate a daily audio digest for bioRxiv papers.

Reads cached metadata (and any downloaded news.md / summary.md) for a given
date and produces an MP3 file at storage/Biorxiv_papers/{date}/digest.mp3.

Run this after fetch_biorxiv.py so metadata is available.

Usage
-----
# Generate digest for yesterday (default)
python digest_biorxiv.py

# Generate digest for a specific date
python digest_biorxiv.py --date 2026-03-21

# Regenerate even if digest.mp3 already exists
python digest_biorxiv.py --date 2026-03-21 --refresh

Cron example (fetch metadata then generate digest every day at 06:00)
----------------------------------------------------------------------
0 6 * * * cd /path/to/PDF2Md && .venv/bin/python fetch_biorxiv.py >> logs/fetch.log 2>&1 && .venv/bin/python digest_biorxiv.py >> logs/digest.log 2>&1
"""

import argparse
import os
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

from services.biorxiv import load_cached_papers
from services.tts import build_daily_digest_script, markdown_to_mp3

# Optional: set this env var to copy the finished digest to a fixed location.
# The file is always written as "biorxiv_digest.mp3" so it is overwritten daily.
# Example: export PDF2MD_DIGEST_DEST="/Volumes/Podcasts/biorxiv"
_DEST_DIR: Path | None = (
    Path(os.environ["PDF2MD_DIGEST_DEST"])
    if "PDF2MD_DIGEST_DEST" in os.environ
    else None
)


def generate_digest(target: date, refresh: bool) -> None:
    date_str = target.strftime("%Y-%m-%d")
    out_path = Path("storage/Biorxiv_papers") / date_str / "digest.mp3"

    if out_path.exists() and not refresh:
        print(f"[{date_str}] digest already exists at {out_path} (use --refresh to regenerate)")
        return

    papers = load_cached_papers(date_str)
    if not papers:
        print(f"[{date_str}] no cached papers found — run fetch_biorxiv.py first", file=sys.stderr)
        return

    print(f"[{date_str}] building script for {len(papers)} papers…", flush=True)
    script = build_daily_digest_script(date_str, papers)
    word_count = len(script.split())
    print(f"[{date_str}] script is {word_count} words (~{word_count // 150} min), synthesising…", flush=True)

    mp3 = markdown_to_mp3(script)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(mp3)
    print(f"[{date_str}] digest saved to {out_path} ({len(mp3) // 1024} KB)")

    if _DEST_DIR is not None:
        _DEST_DIR.mkdir(parents=True, exist_ok=True)
        dest = _DEST_DIR / "biorxiv_digest.mp3"
        shutil.copy2(out_path, dest)
        print(f"[{date_str}] copied to {dest}")


def main() -> None:
    yesterday = date.today() - timedelta(days=1)

    parser = argparse.ArgumentParser(
        description="Generate a daily audio digest for cached bioRxiv papers."
    )
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        metavar="YYYY-MM-DD",
        default=yesterday,
        help="Date to generate digest for (default: yesterday)",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Regenerate even if digest.mp3 already exists",
    )
    args = parser.parse_args()

    if args.date > date.today():
        print("Cannot generate digest for a future date.", file=sys.stderr)
        sys.exit(1)

    generate_digest(args.date, refresh=args.refresh)
    print("Done.")


if __name__ == "__main__":
    main()
