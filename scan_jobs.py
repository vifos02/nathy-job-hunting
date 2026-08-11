#!/usr/bin/env python3
"""
Job board scanner for Nathália's job hunt system.

Reads watchlist.json, hits each company's ATS API, filters by target keywords,
and skips anything already logged in evaluated-jobs.csv.

Usage:
    python scan_jobs.py            # scan and record new jobs
    python scan_jobs.py --dry-run  # scan but don't write to evaluated-jobs.csv

Requires: pip install requests

watchlist.json entry formats:
  Greenhouse: {"company": "Figma",   "platform": "greenhouse", "slug": "figma"}
  Lever:      {"company": "Doist",   "platform": "lever",      "slug": "doist"}
  Ashby:      {"company": "Linear",  "platform": "ashby",      "slug": "linear"}
  Workday:    {"company": "AcmeCo",  "platform": "workday",    "tenant": "acmeco", "host": "wd3", "site": "AcmeCo_Careers"}
"""

import argparse
import csv
import json
import sys
import time
from datetime import date
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent
WATCHLIST_PATH = ROOT / "watchlist.json"
SEEN_JOBS_PATH = ROOT / "evaluated-jobs.csv"

# ---------------------------------------------------------------------------
# Keywords — drawn from CLAUDE.md target roles. Case-insensitive substring match.
# ---------------------------------------------------------------------------
TARGET_KEYWORDS = [
    "seo",
    "search engine optimization",
    "content marketing",
    "content manager",
    "content director",
    "content strategist",
    "content lead",
    "digital marketing",
    "growth marketing",
    "growth manager",
    "marketing operations",
    "marketing manager",
    "marketing director",
    "marketing lead",
    "head of marketing",
    "head of seo",
    "head of content",
    "vp marketing",
    "vp of marketing",
]

SEEN_JOBS_HEADERS = ["job_id", "company", "title", "url", "found_date", "matched"]

# ---------------------------------------------------------------------------
# Seen-jobs helpers
# ---------------------------------------------------------------------------

def load_seen_ids() -> set[str]:
    if not SEEN_JOBS_PATH.exists():
        return set()
    with SEEN_JOBS_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {row["job_id"] for row in reader}


def append_seen(rows: list[dict], dry_run: bool) -> None:
    if dry_run or not rows:
        return
    file_exists = SEEN_JOBS_PATH.exists() and SEEN_JOBS_PATH.stat().st_size > 0
    with SEEN_JOBS_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SEEN_JOBS_HEADERS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Keyword filter
# ---------------------------------------------------------------------------

def is_match(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in TARGET_KEYWORDS)


# ---------------------------------------------------------------------------
# ATS fetchers — each returns a list of dicts: {id, title, location, url}
# ---------------------------------------------------------------------------

def fetch_greenhouse(slug: str) -> list[dict]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    jobs = []
    for j in resp.json().get("jobs", []):
        jobs.append({
            "id": str(j["id"]),
            "title": j["title"],
            "location": j.get("location", {}).get("name", ""),
            "url": j["absolute_url"],
        })
    return jobs


def fetch_lever(slug: str) -> list[dict]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    jobs = []
    for j in resp.json():
        jobs.append({
            "id": j["id"],
            "title": j["text"],
            "location": j.get("categories", {}).get("location", ""),
            "url": j["hostedUrl"],
        })
    return jobs


def fetch_ashby(slug: str) -> list[dict]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    jobs = []
    for j in resp.json().get("jobPostings", []):
        jobs.append({
            "id": j["id"],
            "title": j["title"],
            "location": j.get("locationName") or j.get("location", ""),
            "url": j.get("jobUrl", ""),
        })
    return jobs


def fetch_workday(entry: dict) -> list[dict]:
    tenant = entry["tenant"]
    host = entry.get("host", "wd3")
    site = entry["site"]
    api_url = f"https://{tenant}.{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    base_url = f"https://{tenant}.{host}.myworkdayjobs.com"

    jobs = []
    offset = 0
    limit = 20

    while True:
        resp = requests.post(
            api_url,
            headers={"Content-Type": "application/json"},
            json={"limit": limit, "offset": offset},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        postings = data.get("jobPostings", [])
        if not postings:
            break

        for j in postings:
            path = j.get("externalPath", "")
            job_id = path.rstrip("/").split("_")[-1] if "_" in path else path
            jobs.append({
                "id": job_id or path,
                "title": j.get("title", ""),
                "location": j.get("locationsText", ""),
                "url": f"{base_url}{path}" if path else "",
            })

        total = data.get("total", 0)
        offset += limit
        if offset >= total:
            break
        time.sleep(0.5)

    return jobs


FETCHERS = {
    "greenhouse": lambda entry: fetch_greenhouse(entry["slug"]),
    "lever":      lambda entry: fetch_lever(entry["slug"]),
    "ashby":      lambda entry: fetch_ashby(entry["slug"]),
    "workday":    fetch_workday,
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print matches but don't update evaluated-jobs.csv")
    args = parser.parse_args()

    if not WATCHLIST_PATH.exists():
        sys.exit(f"watchlist.json not found at {WATCHLIST_PATH}")

    watchlist: list[dict] = json.loads(WATCHLIST_PATH.read_text())
    seen_ids = load_seen_ids()
    today = date.today().isoformat()

    all_new_seen: list[dict] = []
    matches: list[dict] = []

    print(f"Scanning {len(watchlist)} companies...\n")

    for entry in watchlist:
        company = entry["company"]
        platform = entry.get("platform", "").lower()
        fetcher = FETCHERS.get(platform)

        if not fetcher:
            print(f"  [SKIP] {company}: unknown platform '{platform}'")
            continue

        print(f"  {company} ({platform}) ... ", end="", flush=True)

        try:
            jobs = fetcher(entry)
        except requests.HTTPError as e:
            print(f"HTTP {e.response.status_code}")
            continue
        except Exception as e:
            print(f"ERROR: {e}")
            continue

        new_count = 0
        match_count = 0

        for job in jobs:
            job_id = f"{platform}:{entry.get('slug', entry.get('tenant', ''))}:{job['id']}"

            if job_id in seen_ids:
                continue

            seen_ids.add(job_id)
            matched = is_match(job["title"])

            all_new_seen.append({
                "job_id": job_id,
                "company": company,
                "title": job["title"],
                "url": job["url"],
                "found_date": today,
                "matched": "yes" if matched else "no",
            })
            new_count += 1

            if matched:
                matches.append({
                    "company": company,
                    "title": job["title"],
                    "location": job.get("location", ""),
                    "url": job["url"],
                })
                match_count += 1

        print(f"{new_count} new jobs, {match_count} match{'es' if match_count != 1 else ''}")

    append_seen(all_new_seen, dry_run=args.dry_run)
    if args.dry_run and all_new_seen:
        print(f"\n[dry-run] Would have recorded {len(all_new_seen)} new jobs to evaluated-jobs.csv")

    print()
    if not matches:
        print("No new matching roles found.")
        return

    print(f"{'=' * 62}")
    print(f"  NEW MATCHING ROLES  ({len(matches)} found — {today})")
    print(f"{'=' * 62}")
    for job in matches:
        loc = f"  [{job['location']}]" if job["location"] else ""
        print(f"\n{job['company']}: {job['title']}{loc}")
        print(f"  {job['url']}")

    print(f"\n{'=' * 62}")
    print("Next: paste any posting above into /evaluate to score it.")
    print("      Then /tailor to generate tailored materials.")


if __name__ == "__main__":
    main()
