#!/usr/bin/env python3
"""
API-based job board scanner for Nathália's job hunt system.

Runs locally on your Mac — twice a day (morning and mid-afternoon).
Pair with browser_search.py which covers Indeed, LinkedIn, and Remote.co.

Always git pull before running to sync the dedup list.

Reads watchlist.json, hits each company's ATS API, filters by target keywords,
and skips anything already logged in evaluated-jobs.csv.

Usage:
    python scan_jobs.py                   # scan ATS sources + aggregators
    python scan_jobs.py --dry-run         # print matches, don't write files
    python scan_jobs.py --ats-only        # skip aggregators
    python scan_jobs.py --aggregators-only  # skip watchlist ATS sources

Requires: pip install requests

watchlist.json entry formats:
  Greenhouse: {"company": "Figma",   "platform": "greenhouse", "slug": "figma"}
  Lever:      {"company": "Doist",   "platform": "lever",      "slug": "doist"}
  Ashby:      {"company": "Linear",  "platform": "ashby",      "slug": "linear"}
  Workday:    {"company": "AcmeCo",  "platform": "workday",    "tenant": "acmeco", "host": "wd3", "site": "AcmeCo_Careers"}
  Breezy:     {"company": "Acme",    "platform": "breezy",     "slug": "acme"}
              slug = subdomain of the company's Breezy board (e.g. veta-virtual-inc.breezy.hr → "veta-virtual-inc")
"""

import argparse
import csv
import hashlib
import json
import sys
import time
import xml.etree.ElementTree as ET
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

SEEN_JOBS_HEADERS = ["job_id", "company", "title", "url", "found_date", "matched", "source"]

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


def fetch_gupy(slug: str) -> list[dict]:
    url = f"https://{slug}.gupy.io/api/jobs"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    jobs = []
    for j in resp.json().get("data", []):
        job_id = str(j.get("id", ""))
        jobs.append({
            "id": job_id,
            "title": j.get("name", ""),
            "location": j.get("city") or j.get("state") or "",
            "url": j.get("jobUrl") or f"https://{slug}.gupy.io/jobs/{job_id}",
        })
    return jobs


def fetch_breezy(slug: str) -> list[dict]:
    url = f"https://{slug}.breezy.hr/json"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    jobs = []
    for j in resp.json():
        if not isinstance(j, dict):
            continue
        job_id = str(j.get("_id", ""))
        loc = j.get("location") or {}
        jobs.append({
            "id": job_id,
            "title": j.get("name", ""),
            "location": loc.get("name", "") if isinstance(loc, dict) else "",
            "url": f"https://{slug}.breezy.hr/p/{job_id}",
        })
    return jobs


def fetch_workable(slug: str) -> list[dict]:
    url = f"https://apply.workable.com/api/v3/accounts/{slug}/jobs"
    resp = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json={"query": "", "location": [], "department": [], "worktype": [], "remote": []},
        timeout=15,
    )
    resp.raise_for_status()
    jobs = []
    for j in resp.json().get("results", []):
        shortcode = j.get("shortcode", "")
        loc = j.get("location") or {}
        jobs.append({
            "id": shortcode or j.get("id", ""),
            "title": j.get("title", ""),
            "location": loc.get("city", "") if isinstance(loc, dict) else "",
            "url": j.get("url") or f"https://apply.workable.com/{slug}/j/{shortcode}",
        })
    return jobs


# ---------------------------------------------------------------------------
# Aggregator fetchers — keyword-filtered, not company-specific
# ---------------------------------------------------------------------------

def fetch_remoteok() -> list[dict]:
    resp = requests.get(
        "https://remoteok.com/remote-jobs.json",
        headers={"User-Agent": "nathy-job-hunter/1.0"},
        timeout=15,
    )
    resp.raise_for_status()
    jobs = []
    for j in resp.json():
        if not isinstance(j, dict) or "id" not in j:
            continue
        title = j.get("position", "")
        if not is_match(title):
            continue
        jobs.append({
            "id": f"remoteok:{j['id']}",
            "company": j.get("company", "Unknown"),
            "title": title,
            "location": "Remote",
            "url": j.get("url", f"https://remoteok.com/l/{j['id']}"),
        })
    return jobs


def fetch_remotive() -> list[dict]:
    resp = requests.get(
        "https://remotive.com/api/remote-jobs?category=marketing",
        timeout=15,
    )
    resp.raise_for_status()
    jobs = []
    for j in resp.json().get("jobs", []):
        title = j.get("title", "")
        if not is_match(title):
            continue
        jobs.append({
            "id": f"remotive:{j['id']}",
            "company": j.get("company_name", "Unknown"),
            "title": title,
            "location": j.get("candidate_required_location", "Remote"),
            "url": j.get("url", ""),
        })
    return jobs


def fetch_workingnomads() -> list[dict]:
    resp = requests.get(
        "https://www.workingnomads.com/api/exposed_jobs/?category=digital-marketing",
        timeout=15,
    )
    resp.raise_for_status()
    jobs = []
    for j in resp.json():
        title = j.get("title", "")
        if not is_match(title):
            continue
        jobs.append({
            "id": f"workingnomads:{j['id']}",
            "company": j.get("company", "Unknown"),
            "title": title,
            "location": j.get("region", "Remote"),
            "url": j.get("url", ""),
        })
    return jobs


def fetch_weworkremotely() -> list[dict]:
    resp = requests.get(
        "https://weworkremotely.com/categories/remote-marketing-jobs.rss",
        timeout=15,
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    jobs = []
    for item in root.findall(".//item"):
        title_el = item.find("title")
        link_el  = item.find("link")
        guid_el  = item.find("guid")
        if title_el is None:
            continue
        full_title = title_el.text or ""
        # WWR title format: "Company Name: Job Title"
        if ": " in full_title:
            company, title = full_title.split(": ", 1)
        else:
            company, title = "Unknown", full_title
        if not is_match(title):
            continue
        href = (link_el.text if link_el is not None else "") or \
               (guid_el.text if guid_el is not None else "")
        job_id = "wwr:" + hashlib.sha1(href.encode()).hexdigest()[:12]
        jobs.append({
            "id": job_id,
            "company": company.strip(),
            "title": title.strip(),
            "location": "Remote",
            "url": href,
        })
    return jobs


FETCHERS = {
    "greenhouse": lambda entry: fetch_greenhouse(entry["slug"]),
    "lever":      lambda entry: fetch_lever(entry["slug"]),
    "ashby":      lambda entry: fetch_ashby(entry["slug"]),
    "workday":    fetch_workday,
    "gupy":       lambda entry: fetch_gupy(entry["slug"]),
    "workable":   lambda entry: fetch_workable(entry["slug"]),
    "breezy":     lambda entry: fetch_breezy(entry["slug"]),
}

AGGREGATORS = [
    ("Remote OK",        "remoteok",        fetch_remoteok),
    ("Remotive",         "remotive",        fetch_remotive),
    ("Working Nomads",   "workingnomads",   fetch_workingnomads),
    ("We Work Remotely", "weworkremotely",  fetch_weworkremotely),
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process_jobs(jobs: list, job_id_prefix: str, company: str, source: str,
                 seen_ids: set, today: str) -> tuple[list, list]:
    """Deduplicate and classify a list of raw job dicts. Returns (new_seen, matches)."""
    new_seen, matches = [], []
    for job in jobs:
        job_id = f"{job_id_prefix}:{job['id']}"
        if job_id in seen_ids:
            continue
        seen_ids.add(job_id)
        matched = is_match(job["title"])
        row = {
            "job_id": job_id,
            "company": company or job.get("company", "Unknown"),
            "title": job["title"],
            "url": job["url"],
            "found_date": today,
            "matched": "yes" if matched else "no",
            "source": source,
        }
        new_seen.append(row)
        if matched:
            matches.append(row)
    return new_seen, matches


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print matches but don't update evaluated-jobs.csv")
    parser.add_argument("--ats-only", action="store_true",
                        help="Skip aggregators, scan watchlist ATS sources only")
    parser.add_argument("--aggregators-only", action="store_true",
                        help="Skip watchlist ATS sources, scan aggregators only")
    args = parser.parse_args()

    if not WATCHLIST_PATH.exists():
        sys.exit(f"watchlist.json not found at {WATCHLIST_PATH}")

    watchlist: list[dict] = json.loads(WATCHLIST_PATH.read_text())
    seen_ids = load_seen_ids()
    today = date.today().isoformat()

    all_new_seen: list[dict] = []
    all_matches: list[dict] = []

    # --- Watchlist ATS scan ---
    if not args.aggregators_only:
        print(f"Scanning {len(watchlist)} companies (ATS)...\n")
        for entry in watchlist:
            company  = entry["company"]
            platform = entry.get("platform", "").lower()
            fetcher  = FETCHERS.get(platform)

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

            prefix = f"{platform}:{entry.get('slug', entry.get('tenant', ''))}"
            new_seen, matches = process_jobs(jobs, prefix, company, platform, seen_ids, today)
            all_new_seen.extend(new_seen)
            all_matches.extend(matches)
            print(f"{len(new_seen)} new, {len(matches)} match{'es' if len(matches) != 1 else ''}")

    # --- Aggregator scan ---
    if not args.ats_only:
        print(f"\nScanning {len(AGGREGATORS)} aggregators...\n")
        for label, source_key, fetcher in AGGREGATORS:
            print(f"  {label} ... ", end="", flush=True)
            try:
                jobs = fetcher()
            except requests.HTTPError as e:
                print(f"HTTP {e.response.status_code}")
                continue
            except Exception as e:
                print(f"ERROR: {e}")
                continue

            new_seen, matches = process_jobs(jobs, source_key, "", source_key, seen_ids, today)
            all_new_seen.extend(new_seen)
            all_matches.extend(matches)
            print(f"{len(new_seen)} new, {len(matches)} match{'es' if len(matches) != 1 else ''}")
            time.sleep(1)

    append_seen(all_new_seen, dry_run=args.dry_run)
    if args.dry_run and all_new_seen:
        print(f"\n[dry-run] Would have recorded {len(all_new_seen)} new jobs to evaluated-jobs.csv")

    print()
    if not all_matches:
        print("No new matching roles found.")
        return

    print(f"{'=' * 62}")
    print(f"  NEW MATCHING ROLES  ({len(all_matches)} found — {today})")
    print(f"{'=' * 62}")
    for job in all_matches:
        src = f"  [via {job['source']}]" if job.get("source") else ""
        print(f"\n{job['company']}: {job['title']}{src}")
        print(f"  {job['url']}")

    print(f"\n{'=' * 62}")
    print("Next: paste any posting above into /evaluate to score it.")
    print("      Then /tailor to generate tailored materials.")


if __name__ == "__main__":
    main()
