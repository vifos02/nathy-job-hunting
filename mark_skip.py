"""
Record manual review decisions to avoid re-processing already-reviewed jobs.

Usage — pass job IDs directly:
    python3 mark_skip.py linkedin:abc123 linkedin:def456

Usage — pass a file with one job_id per line:
    python3 mark_skip.py --file my-skips.txt

Usage — mark all unmatched browser entries as manually reviewed (bulk cleanup):
    python3 mark_skip.py --all-unmatched

What it does:
  Writes a manual-reviews.csv (separate from evaluated-jobs.csv) with columns:
    job_id, date_reviewed, reason

  The prefilter_unscored.py and /digest scripts read this file and suppress
  these job_ids from "unscored" counts and match lists.

Options:
    --reason TEXT    Reason label to record (default: "manual_skip")
    --file FILE      Read job_ids from a text file (one per line)
    --all-unmatched  Mark all browser-finds.json entries with matched=no as reviewed
    --dry-run        Print what would be written, don't write
"""

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
REVIEWS_PATH = ROOT / "manual-reviews.csv"
BROWSER_FINDS_PATH = ROOT / "browser-finds.json"
SEEN_JOBS_PATH = ROOT / "evaluated-jobs.csv"
REVIEWS_HEADERS = ["job_id", "date_reviewed", "reason"]


def load_reviewed() -> set:
    if not REVIEWS_PATH.exists():
        return set()
    with REVIEWS_PATH.open(newline="", encoding="utf-8") as f:
        return {row["job_id"] for row in csv.DictReader(f)}


def write_reviews(job_ids: list[str], reason: str, dry_run: bool) -> int:
    already = load_reviewed()
    today = date.today().isoformat()
    new_rows = [
        {"job_id": jid, "date_reviewed": today, "reason": reason}
        for jid in job_ids
        if jid not in already
    ]
    if not new_rows:
        print("All specified job_ids are already in manual-reviews.csv.")
        return 0
    if dry_run:
        for r in new_rows:
            print(f"[dry-run] would mark: {r['job_id']} ({reason})")
        return len(new_rows)
    file_exists = REVIEWS_PATH.exists() and REVIEWS_PATH.stat().st_size > 0
    with REVIEWS_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEWS_HEADERS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(new_rows)
    return len(new_rows)


def collect_unmatched() -> list[str]:
    ids = []
    if BROWSER_FINDS_PATH.exists():
        for entry in json.loads(BROWSER_FINDS_PATH.read_text()):
            if entry.get("matched") == "no" and entry.get("job_id"):
                ids.append(entry["job_id"])
    if SEEN_JOBS_PATH.exists():
        with SEEN_JOBS_PATH.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("matched") == "no" and row.get("job_id"):
                    ids.append(row["job_id"])
    return list(dict.fromkeys(ids))  # stable dedup, preserve order


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("job_ids", nargs="*", metavar="JOB_ID",
                        help="One or more job_id values to mark as manually reviewed")
    parser.add_argument("--file", metavar="FILE",
                        help="Text file with one job_id per line")
    parser.add_argument("--all-unmatched", action="store_true",
                        help="Mark all unmatched entries in evaluated-jobs.csv and browser-finds.json")
    parser.add_argument("--reason", default="manual_skip",
                        help="Reason label (default: manual_skip)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    job_ids: list[str] = list(args.job_ids)

    if args.file:
        p = Path(args.file)
        if not p.exists():
            sys.exit(f"File not found: {args.file}")
        job_ids.extend(line.strip() for line in p.read_text().splitlines() if line.strip())

    if args.all_unmatched:
        unmatched = collect_unmatched()
        print(f"Found {len(unmatched)} unmatched entries.")
        job_ids.extend(unmatched)

    if not job_ids:
        parser.print_help()
        sys.exit(1)

    job_ids = list(dict.fromkeys(job_ids))  # dedup, preserve order
    written = write_reviews(job_ids, args.reason, args.dry_run)
    action = "Would mark" if args.dry_run else "Marked"
    print(f"{action} {written} job_ids as '{args.reason}' in manual-reviews.csv")


if __name__ == "__main__":
    main()
