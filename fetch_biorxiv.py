"""CLI script to pre-fetch bioRxiv metadata for use with the Streamlit app.

Fetches paper metadata for one or more dates and caches it to disk under
storage/Biorxiv_papers/{date}/.  The Streamlit app reads from this cache,
so running this script before launching the app means metadata is ready
immediately.

Usage
-----
# Fetch yesterday (default)
python fetch_biorxiv.py

# Fetch a specific date
python fetch_biorxiv.py --date 2026-03-21

# Fetch the last N days (already-cached dates are skipped by default)
python fetch_biorxiv.py --days 3

# Fetch a date range
python fetch_biorxiv.py --from 2026-03-18 --to 2026-03-21

# Force re-fetch even if already cached (e.g. after changing categories)
python fetch_biorxiv.py --days 7 --refresh

Cron example (fetch yesterday's papers and generate digest every day at 06:00)
------------------------------------------------------------------------------
0 6 * * * cd /path/to/PDF2Md && .venv/bin/python fetch_biorxiv.py >> logs/fetch.log 2>&1 && .venv/bin/python digest_biorxiv.py >> logs/digest.log 2>&1
"""

import argparse
import sys
from datetime import date, timedelta

from services.biorxiv import (
    fetch_papers,
    is_cached,
    load_categories,
    save_metadata,
)


def date_range(start: date, end: date) -> list[date]:
    days = (end - start).days
    return [start + timedelta(days=i) for i in range(days + 1)]


def fetch_date(target: date, categories: list[str], skip_cached: bool) -> None:
    date_str = target.strftime("%Y-%m-%d")

    if skip_cached:
        # Count already-cached papers for this date
        from services.biorxiv import load_cached_papers
        existing = load_cached_papers(date_str)
        if existing:
            print(f"[{date_str}] skipped — {len(existing)} papers already cached")
            return

    print(f"[{date_str}] fetching across {len(categories)} categories…", flush=True)
    try:
        papers = fetch_papers(date_str, categories)
    except Exception as exc:
        print(f"[{date_str}] ERROR fetching: {exc}", file=sys.stderr)
        return

    new_count = 0
    for paper in papers:
        if not is_cached(date_str, paper["doi"]):
            save_metadata(paper, date_str)
            new_count += 1

    print(
        f"[{date_str}] {len(papers)} papers found, "
        f"{new_count} newly cached, "
        f"{len(papers) - new_count} already existed"
    )


def main() -> None:
    yesterday = date.today() - timedelta(days=1)

    parser = argparse.ArgumentParser(
        description="Pre-fetch bioRxiv metadata for the PDF2Md app."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--date",
        type=date.fromisoformat,
        metavar="YYYY-MM-DD",
        help="Fetch a single date (default: yesterday)",
    )
    group.add_argument(
        "--days",
        type=int,
        metavar="N",
        help="Fetch the last N days ending yesterday",
    )
    group.add_argument(
        "--from",
        dest="date_from",
        type=date.fromisoformat,
        metavar="YYYY-MM-DD",
        help="Start of date range (use with --to)",
    )
    parser.add_argument(
        "--to",
        dest="date_to",
        type=date.fromisoformat,
        metavar="YYYY-MM-DD",
        default=yesterday,
        help="End of date range (default: yesterday)",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-fetch dates that already have cached metadata (e.g. after changing categories)",
    )
    args = parser.parse_args()

    categories = load_categories()
    if not categories:
        print("No categories configured. Edit biorxiv_categories.txt first.", file=sys.stderr)
        sys.exit(1)
    print(f"Categories: {', '.join(categories)}")

    # Build list of dates to fetch
    if args.date:
        dates = [args.date]
    elif args.days:
        dates = date_range(yesterday - timedelta(days=args.days - 1), yesterday)
    elif args.date_from:
        dates = date_range(args.date_from, args.date_to)
    else:
        dates = [yesterday]

    # Refuse to fetch future dates
    dates = [d for d in dates if d <= date.today()]
    if not dates:
        print("No valid dates to fetch (future dates are excluded).")
        sys.exit(0)

    for d in dates:
        fetch_date(d, categories, skip_cached=not args.refresh)

    print("Done.")


if __name__ == "__main__":
    main()
