"""
Sync Tier 1 companies from companies.md into watchlist.json.

Usage:
    python3 sync_watchlist.py           # show what's in companies.md but not watchlist.json
    python3 sync_watchlist.py --add     # interactive: add missing entries one by one

The scanner (scan_jobs.py) reads watchlist.json, not companies.md directly. This script
bridges the two by reporting which Tier 1 (🔴) companies have no watchlist entry, then
letting you record their ATS platform and slug.

ATS platform values:
    greenhouse   slug = company's Greenhouse board slug (e.g. "hotmartcareersen")
    lever        slug = company's Lever board slug (e.g. "doist")
    ashby        slug = company's Ashby board slug (e.g. "buffer")
    workday      tenant + host (wd1/wd3/wd103) + site required
    gupy         slug = company's Gupy slug (e.g. "magazineluiza")
    workable     slug = company's Workable board slug
    breezy       slug = subdomain of the breezy.hr board
    personio     slug = subdomain of the personio board
    teamtailor   slug = company's Teamtailor slug
    bamboohr     slug = company's BambooHR slug
    other        careers URL recorded but scanner will not poll automatically
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
COMPANIES_PATH = ROOT / "companies.md"
WATCHLIST_PATH = ROOT / "watchlist.json"


def load_watchlist() -> list[dict]:
    if not WATCHLIST_PATH.exists():
        return []
    return json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))


def save_watchlist(data: list[dict]) -> None:
    WATCHLIST_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def watched_companies(watchlist: list[dict]) -> set[str]:
    return {entry["company"].lower().strip() for entry in watchlist}


def parse_tier1_companies(path: Path) -> list[dict]:
    """Parse companies.md for Tier 1 (🔴) rows. Returns list of {name, url, notes}."""
    text = path.read_text(encoding="utf-8")
    results = []
    for line in text.splitlines():
        # Match Markdown table rows with 🔴 and a URL
        if "🔴" not in line:
            continue
        # Split pipe-delimited row
        cols = [c.strip() for c in line.split("|") if c.strip()]
        if len(cols) < 2:
            continue
        company = cols[0].strip()
        # Extract URL from any column
        url_match = re.search(r"https?://[^\s\)]+", line)
        url = url_match.group(0).rstrip(").,") if url_match else ""
        notes = cols[-1] if len(cols) >= 3 else ""
        if company and company not in ("Company", "---"):
            results.append({"name": company, "url": url, "notes": notes})
    return results


def guess_platform(url: str) -> tuple[str, str]:
    """Try to guess ATS platform and slug from a careers URL."""
    if not url:
        return "unknown", ""
    if "greenhouse.io" in url or "boards.greenhouse" in url:
        m = re.search(r"boards\.greenhouse\.io/([^/?#]+)", url)
        return "greenhouse", m.group(1) if m else ""
    if "jobs.lever.co" in url:
        m = re.search(r"jobs\.lever\.co/([^/?#]+)", url)
        return "lever", m.group(1) if m else ""
    if "jobs.ashby" in url:
        m = re.search(r"jobs\.ashby(?:hq)?\.com/([^/?#]+)", url)
        return "ashby", m.group(1) if m else ""
    if "gupy.io" in url:
        m = re.search(r"([^./]+)\.gupy\.io|gupy\.io/([^/?#]+)", url)
        if m:
            slug = m.group(1) or m.group(2)
            return "gupy", slug or ""
    if "workable.com" in url or "apply.workable.com" in url:
        m = re.search(r"(?:jobs|apply)\.workable\.com/([^/?#]+)", url)
        return "workable", m.group(1) if m else ""
    if "breezy.hr" in url:
        m = re.search(r"([^./]+)\.breezy\.hr", url)
        return "breezy", m.group(1) if m else ""
    if "personio" in url and "jobs.personio" in url:
        m = re.search(r"([^./]+)\.jobs\.personio", url)
        return "personio", m.group(1) if m else ""
    if "workday.com" in url or "myworkdayjobs.com" in url:
        return "workday", "(needs tenant/host/site — see scan_jobs.py)"
    return "other", ""


def main() -> None:
    add_mode = "--add" in sys.argv

    watchlist = load_watchlist()
    watched = watched_companies(watchlist)

    tier1 = parse_tier1_companies(COMPANIES_PATH)
    missing = [c for c in tier1 if c["name"].lower() not in watched]

    if not missing:
        print("All Tier 1 companies in companies.md are already in watchlist.json.")
        return

    print(f"\n{len(missing)} Tier 1 companies not yet in watchlist.json:\n")
    for i, c in enumerate(missing, 1):
        platform, slug = guess_platform(c["url"])
        print(f"  {i:2}. {c['name']}")
        print(f"       URL:      {c['url'] or '(none)'}")
        print(f"       Platform: {platform}  slug: {slug or '(unknown)'}")
        if c["notes"]:
            print(f"       Notes:    {c['notes'][:80]}")
        print()

    if not add_mode:
        print("Run with --add to step through each missing company and add it to watchlist.json.")
        return

    # Interactive add mode
    for c in missing:
        platform, slug = guess_platform(c["url"])
        print(f"\n--- {c['name']} ---")
        print(f"  Careers URL: {c['url']}")
        print(f"  Auto-guessed: platform={platform}, slug={slug}")
        choice = input("  Add to watchlist? [y/n/s=skip]: ").strip().lower()
        if choice == "y":
            platform_in = input(f"  Platform [{platform}]: ").strip() or platform
            if platform_in == "workday":
                tenant = input("  Workday tenant: ").strip()
                host = input("  Workday host (wd1/wd3/wd103): ").strip()
                site = input("  Workday site ID: ").strip()
                entry = {
                    "company": c["name"],
                    "platform": "workday",
                    "tenant": tenant,
                    "host": host,
                    "site": site,
                }
            else:
                slug_in = input(f"  Slug [{slug}]: ").strip() or slug
                entry = {"company": c["name"], "platform": platform_in, "slug": slug_in}
            watchlist.append(entry)
            save_watchlist(watchlist)
            print(f"  Added: {json.dumps(entry)}")
        elif choice == "s" or choice == "n":
            print("  Skipped.")

    print("\nwatchlist.json updated.")


if __name__ == "__main__":
    main()
