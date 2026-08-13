#!/usr/bin/env python3
"""
list_unscored.py — Print all matched=yes jobs that have no evaluation file yet.
No API calls. Reads evaluated-jobs.csv and evaluations/*.md only.

Usage:
    python list_unscored.py              # print all unscored, grouped by source
    python list_unscored.py --csv        # output as CSV
    python list_unscored.py --source greenhouse   # filter by source prefix
"""

import csv
import re
import sys
from pathlib import Path

BASE = Path(__file__).parent

def load_scored_ids():
    ids = set()
    for f in (BASE / "evaluations").glob("*.md"):
        m = re.search(r"<!-- job_id: (.+?) -->", f.read_text())
        if m:
            ids.add(m.group(1).strip())
    return ids

def load_unscored(source_filter=None):
    scored = load_scored_ids()
    rows = []
    with open(BASE / "evaluated-jobs.csv", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if row["matched"] != "yes":
                continue
            if row["job_id"] in scored:
                continue
            if source_filter and not row["job_id"].startswith(source_filter):
                continue
            rows.append(row)
    return rows

def source_prefix(job_id):
    parts = job_id.split(":")
    return parts[0] if parts else "unknown"

def main():
    as_csv = "--csv" in sys.argv
    source_filter = None
    for arg in sys.argv[1:]:
        if arg.startswith("--source="):
            source_filter = arg.split("=", 1)[1]
        elif arg == "--source" and sys.argv.index(arg) + 1 < len(sys.argv):
            source_filter = sys.argv[sys.argv.index(arg) + 1]

    rows = load_unscored(source_filter)

    if as_csv:
        writer = csv.writer(sys.stdout)
        writer.writerow(["source", "company", "title", "url", "found_date", "job_id"])
        for r in sorted(rows, key=lambda x: (source_prefix(x["job_id"]), x["company"])):
            writer.writerow([
                source_prefix(r["job_id"]),
                r["company"],
                r["title"],
                r["url"],
                r["found_date"],
                r["job_id"],
            ])
        return

    # Group by source for readable terminal output
    from collections import defaultdict
    by_source = defaultdict(list)
    for r in rows:
        by_source[source_prefix(r["job_id"])].append(r)

    total = sum(len(v) for v in by_source.values())
    print(f"\n{'='*70}")
    print(f"UNSCORED MATCHED JOBS — {total} total")
    if source_filter:
        print(f"(filtered to source: {source_filter})")
    print(f"{'='*70}\n")

    for src in sorted(by_source):
        group = sorted(by_source[src], key=lambda x: x["company"])
        print(f"── {src.upper()} ({len(group)}) {'─'*(50 - len(src))}")
        for r in group:
            print(f"  {r['company']}")
            print(f"  {r['title']}")
            print(f"  {r['url']}")
            print(f"  Found: {r['found_date']}  |  ID: {r['job_id']}")
            print()

    print(f"Total: {total} unscored matched jobs")

if __name__ == "__main__":
    main()
