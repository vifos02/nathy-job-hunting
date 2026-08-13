#!/usr/bin/env python3
"""
list_unscored.py — Print all matched=yes jobs that have no evaluation file yet.
No API calls. Reads evaluated-jobs.csv, browser-finds.json, and evaluations/*.md.

Usage:
    python list_unscored.py              # print all unscored, grouped by source
    python list_unscored.py --csv        # output as CSV
    python list_unscored.py --source linkedin    # filter by source prefix
    python list_unscored.py --api-only   # only API scan results (evaluated-jobs.csv)
    python list_unscored.py --browser-only  # only browser scan results (browser-finds.json)
"""

import csv
import json
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

def load_unscored(source_filter=None, api_only=False, browser_only=False):
    scored = load_scored_ids()
    rows = []

    if not browser_only:
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

    if not api_only:
        bf = BASE / "browser-finds.json"
        if bf.exists():
            for entry in json.loads(bf.read_text()):
                if entry.get("matched") != "yes":
                    continue
                if entry["job_id"] in scored:
                    continue
                if source_filter and not entry["job_id"].startswith(source_filter):
                    continue
                rows.append(entry)

    # Deduplicate by job_id (a job could appear in both files)
    seen = set()
    deduped = []
    for r in rows:
        if r["job_id"] not in seen:
            seen.add(r["job_id"])
            deduped.append(r)
    return deduped

def source_prefix(job_id):
    parts = job_id.split(":")
    return parts[0] if parts else "unknown"

def main():
    as_csv = "--csv" in sys.argv
    api_only = "--api-only" in sys.argv
    browser_only = "--browser-only" in sys.argv
    source_filter = None
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg.startswith("--source="):
            source_filter = arg.split("=", 1)[1]
        elif arg == "--source" and i < len(sys.argv) - 1:
            source_filter = sys.argv[i + 1]

    rows = load_unscored(source_filter, api_only=api_only, browser_only=browser_only)

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
