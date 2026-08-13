#!/usr/bin/env python3
"""
Browser-based job scanner for sites that block API access.

Covers: Indeed (remote filter, 14 days), LinkedIn (remote, past 7 days), Remote.co, InfoJobs (remote, Spain/LATAM).

MUST RUN LOCALLY on your Mac — not in the Claude Web remote session.
The remote session's network egress policy blocks indeed.com, linkedin.com, and remote.co.
scan_jobs.py handles API-accessible sources and runs in the remote session.

Standard run cycle (twice a day):
    git pull                          # sync dedup list before running
    python browser_search.py
    git add evaluated-jobs.csv browser-finds.json
    git commit -m "browser scan $(date +%Y-%m-%d)"
    git push

Matches append to evaluated-jobs.csv (dedup record shared with scan_jobs.py)
and write to browser-finds.json (matches only, for /digest review).

Usage:
    python browser_search.py                     # run all sources
    python browser_search.py --dry-run           # print matches, no writes
    python browser_search.py --source indeed     # one source only
    python browser_search.py --source linkedin
    python browser_search.py --source remoteco

Requires: pip install playwright
"""

import argparse
import csv
import glob
import hashlib
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("playwright not installed. Run: pip install playwright")

ROOT = Path(__file__).parent
SEEN_JOBS_PATH = ROOT / "evaluated-jobs.csv"
BROWSER_FINDS_PATH = ROOT / "browser-finds.json"

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
    "social media marketing",
    "demand generation",
    # Portuguese-language equivalents — surfaces Brazilian boards (LinkedIn BR, Gupy) in PT
    "gerente de marketing",
    "gerente de marketing digital",
    "gerente de seo",
    "gerente de conteúdo",
    "gerente de growth",
    "head de marketing",
    "head de seo",
    "head de conteúdo",
    "head de growth",
    "diretor de marketing",
    "diretora de marketing",
    "diretor de marketing digital",
    "especialista em seo",
    "especialista em marketing",
    "especialista em marketing digital",
    "analista sênior de seo",
    "analista sênior de marketing",
    "analista de seo",
    "analista de marketing digital",
    "gerente de operações de marketing",
    "líder de marketing",
    "líder de seo",
    "líder de conteúdo",
    # Spanish-language equivalents — surfaces InfoJobs and LATAM board postings
    "marketing digital",
    "director de marketing",
    "directora de marketing",
    "jefe de marketing",
    "responsable seo",
    "responsable de marketing",
    "especialista en seo",
    "especialista en marketing",
]

# Applied after TARGET_KEYWORDS match — mirrors scan_jobs.py / evaluate_matches.py
SKIP_TITLE_WORDS = [
    "junior", " jr ", "associate", "coordinator", "intern", "entry level",
    "developer", "engineer", "data scientist", "data analyst",
    "ppc specialist", "sem specialist", "paid search specialist", ", sem",
    "product marketing", "lifecycle marketing", "account based",
    "field marketing", "event marketing", "enablement", "affiliate",
    # Paid/specialist disciplines outside target scope
    "performance marketing",
    "trade marketing",
    "partner marketing",
    "channel marketing",
    "influencer marketing",
    "paid media",
    "paid social",
    "communications manager",
    "public relations",
    "japan", "tokyo", "singapore", "apac", "asia pacific",
    "china", "hong kong", "korea", "sydney", "australia",
    "indonesia", "jakarta", "malaysia", "kuala lumpur", "philippines",
    "são paulo", "sao paulo", "tel aviv",
    "new york,", "san francisco,", "austin,", "chicago,", "los angeles,",
    "seattle,", "boston,", "denver,", "miami,", "atlanta,",
    "office manager",
    # Portuguese-language blocklist — junior/entry-level titles in PT
    "coordenador de marketing", "coordenadora de marketing",
    "assistente de marketing", "estagiário", "estagiária", "júnior",
]
SKIP_INDUSTRY_WORDS = [
    "crypto", "cryptocurrency", "bitcoin", "blockchain",
    "betting", "gambling", "casino", "adult",
]
# Only explicit auth language in titles — timezone alone is not a block (Brazil = UTC-3)
US_AUTH_TITLE_SIGNALS = [
    "(us only)", "us citizens only", "us citizenship required",
    "california,", "us northeast,", "us south,", "us midwest,",
]

SEARCH_QUERIES = [
    # Core discipline queries — run worldwide
    "seo manager",
    "content marketing manager",
    "digital marketing manager",
    "growth marketing manager",
    "head of content",
    "head of seo",
    "marketing operations manager",
    # LATAM-focused — surfaces roles targeting her background and Brazil move
    "latam marketing manager",
    "marketing manager latam",
    "marketing manager brazil",
    "seo manager brazil",
    "content marketing latam",
    # Global/international signals — prioritises truly remote-worldwide postings
    "global seo manager",
    "global content marketing manager",
    # Brazil-specific — moving November 2026, Brazilian national, any Brazil-based role is in scope
    "seo manager brazil remote",
    "content marketing brazil remote",
    "digital marketing brazil remote",
    "marketing manager brazil remote",
    "remote marketing brazil",
    "marketing brasil",
    "seo brasil",
    # Portuguese language signals — native speaker, strong differentiator for LATAM/global roles
    "marketing manager portuguese speaking",
    "seo manager portuguese speaking",
    "content marketing portuguese speaking",
    "portuguese speaking marketing",
    # Portuguese-market scope signals
    "seo portuguese market",
    "content manager portuguese",
    "digital marketing portuguese",
    # Portugal-based remote — viable once EU citizenship clears
    "marketing manager portugal",
    "seo manager portugal",
    # Portuguese-language titles — indexes Brazilian boards (LinkedIn BR, Gupy)
    "gerente de marketing",
    "gerente de marketing digital",
    "gerente de seo",
    "gerente de conteúdo",
    "gerente de growth",
    "head de marketing",
    "head de seo",
    "head de conteúdo",
    "diretor de marketing",
    "especialista em seo",
    "especialista em marketing digital",
    "analista sênior de seo",
    "analista de marketing digital",
    "gerente de operações de marketing",
    "líder de marketing",
    "líder de seo",
    # Spanish-language LATAM titles (supplement InfoJobs queries)
    "director de marketing",
    "jefe de marketing",
    "especialista en seo",
    "especialista en marketing digital",
]

# InfoJobs-specific query list — focused on what the Spanish board is good at:
# international remote postings indexed in English + Spanish-language roles from Spain/LATAM.
# Kept shorter than SEARCH_QUERIES to avoid running 30 near-useless queries on a regional board.
INFOJOBS_QUERIES = [
    "seo manager",
    "content marketing manager",
    "digital marketing manager",
    "growth marketing manager",
    "head of content",
    "head of seo",
    "marketing operations manager",
    # Spanish-language variants
    "marketing digital",
    "director marketing",
    "responsable de marketing",
    "responsable seo",
    # LATAM / Portuguese signals
    "marketing manager latam",
    "marketing manager brazil",
    "content marketing portuguese",
    "marketing manager portuguese speaking",
    # Portuguese-language titles — InfoJobs indexes Brazil/Portugal postings
    "gerente de marketing",
    "gerente de marketing digital",
    "gerente de seo",
    "head de marketing",
    "director de marketing",
    "especialista en seo",
    "especialista en marketing digital",
]

SEEN_JOBS_HEADERS = ["job_id", "company", "title", "url", "found_date", "matched", "source"]


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

_US_STATES = {
    "al","ak","az","ar","ca","co","ct","de","fl","ga","hi","id","il","in",
    "ia","ks","ky","la","me","md","ma","mi","mn","ms","mo","mt","ne","nv",
    "nh","nj","nm","ny","nc","nd","oh","ok","or","pa","ri","sc","sd","tn",
    "tx","ut","vt","va","wa","wv","wi","wy","dc",
}

def _is_us_location(location: str) -> bool:
    """Return True if the location field indicates a US-specific role."""
    import re as _re
    loc = location.lower().strip()
    if not loc or loc in ("remote", "worldwide", "global", "anywhere"):
        return False
    if "united states" in loc or loc == "usa":
        return True
    m = _re.search(r",\s*([a-z]{2})\s*$", loc)
    if m and m.group(1) in _US_STATES:
        return True
    return False


def url_id(url: str) -> str:
    """12-char SHA1 of the URL — stable job ID for browser-found jobs."""
    return hashlib.sha1(url.encode()).hexdigest()[:12]


def is_match(title: str, company: str = "") -> bool:
    t = title.lower()
    c = company.lower()
    if not any(kw in t for kw in TARGET_KEYWORDS):
        return False
    if any(kw in t for kw in SKIP_TITLE_WORDS):
        return False
    if any(kw in c for kw in SKIP_INDUSTRY_WORDS):
        return False
    if any(kw in t for kw in US_AUTH_TITLE_SIGNALS):
        return False
    return True


def load_seen_ids() -> set:
    ids = set()
    if SEEN_JOBS_PATH.exists():
        with SEEN_JOBS_PATH.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("job_id"):
                    ids.add(row["job_id"])
    if BROWSER_FINDS_PATH.exists():
        for entry in json.loads(BROWSER_FINDS_PATH.read_text()):
            if entry.get("job_id"):
                ids.add(entry["job_id"])
    return ids


def append_to_csv(rows: list, dry_run: bool) -> None:
    if dry_run or not rows:
        return
    file_exists = SEEN_JOBS_PATH.exists() and SEEN_JOBS_PATH.stat().st_size > 0
    with SEEN_JOBS_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SEEN_JOBS_HEADERS, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)


def save_browser_finds(new_matches: list, dry_run: bool) -> None:
    if dry_run:
        return
    existing = []
    if BROWSER_FINDS_PATH.exists():
        existing = json.loads(BROWSER_FINDS_PATH.read_text())
    existing.extend(new_matches)
    BROWSER_FINDS_PATH.write_text(json.dumps(existing, indent=2, ensure_ascii=False))


def find_chromium_executable() -> str | None:
    base = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
    if not base:
        return None
    patterns = [
        f"{base}/chromium-*/chrome-linux/chrome",
        f"{base}/chromium/chrome-linux/chrome",
        f"{base}/chromium-*/chrome",
    ]
    for pattern in patterns:
        hits = sorted(glob.glob(pattern))
        if hits:
            return hits[-1]  # newest revision
    return None


# ---------------------------------------------------------------------------
# Indeed
# ---------------------------------------------------------------------------

def scrape_indeed(page, seen_ids: set, today: str) -> tuple:
    all_new, matches = [], []
    found_urls: set = set()

    for query in SEARCH_QUERIES:
        q = query.replace(" ", "+")
        # sc= param applies the "Remote" facet; fromage=14 = past 14 days
        url = (
            f"https://www.indeed.com/jobs?q={q}"
            f"&sc=0kf%3Aattr%28DSQF7%29%3B&fromage=14"
        )
        print(f"    {query!r} ... ", end="", flush=True)

        try:
            page.goto(url, timeout=25000, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)
        except Exception as e:
            print(f"SKIP ({type(e).__name__})")
            continue

        body = page.content().lower()
        if "captcha" in body[:2000] or "are you a robot" in body[:2000]:
            print("BLOCKED (CAPTCHA) — skipping Indeed for this run")
            break

        cards = page.query_selector_all("div.job_seen_beacon")
        if not cards:
            cards = page.query_selector_all("li[class*='job']")

        new_count = 0
        for card in cards:
            try:
                title_el = (
                    card.query_selector("h2.jobTitle a span[title]")
                    or card.query_selector("h2.jobTitle a")
                    or card.query_selector("h2.jobTitle span[title]")
                )
                if not title_el:
                    continue
                title = (
                    title_el.get_attribute("title")
                    or title_el.inner_text()
                ).strip()
                if not title:
                    continue

                company_el = (
                    card.query_selector("[data-testid='company-name']")
                    or card.query_selector(".companyName")
                )
                company = company_el.inner_text().strip() if company_el else "Unknown"

                # Skip US-location roles before dedup
                location_el = (
                    card.query_selector("[data-testid='text-location']")
                    or card.query_selector(".companyLocation")
                    or card.query_selector(".company_location")
                )
                location = location_el.inner_text().strip() if location_el else ""
                if _is_us_location(location):
                    continue

                link_el = card.query_selector("h2.jobTitle a")
                href = (link_el.get_attribute("href") or "") if link_el else ""
                if href.startswith("/"):
                    href = "https://www.indeed.com" + href
                # Strip tracking after jk= param — that's the stable ID
                if "jk=" in href:
                    jk = href.split("jk=")[1].split("&")[0]
                    href = f"https://www.indeed.com/viewjob?jk={jk}"
                if not href or href in found_urls:
                    continue
                found_urls.add(href)

                job_id = f"indeed:{url_id(href)}"
                if job_id in seen_ids:
                    continue
                seen_ids.add(job_id)

                matched = is_match(title, company)
                row = {
                    "job_id": job_id,
                    "company": company,
                    "title": title,
                    "url": href,
                    "found_date": today,
                    "matched": "yes" if matched else "no",
                    "source": "indeed",
                }
                all_new.append(row)
                new_count += 1
                if matched:
                    matches.append(row)
            except Exception:
                continue

        print(f"{new_count} new")
        time.sleep(2)

    return all_new, matches


# ---------------------------------------------------------------------------
# LinkedIn
# ---------------------------------------------------------------------------

def scrape_linkedin(page, seen_ids: set, today: str) -> tuple:
    all_new, matches = [], []
    found_urls: set = set()

    for query in SEARCH_QUERIES:
        q = query.replace(" ", "%20")
        # f_WT=2 = remote; geoId=92000000 = Worldwide; f_TPR=r604800 = past 7 days
        url = (
            f"https://www.linkedin.com/jobs/search/"
            f"?keywords={q}&f_WT=2&geoId=92000000&f_TPR=r604800"
        )
        print(f"    {query!r} ... ", end="", flush=True)

        try:
            page.goto(url, timeout=25000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
        except Exception as e:
            print(f"SKIP ({type(e).__name__})")
            continue

        title_text = page.title().lower()
        if "authwall" in page.url or "sign in" in title_text or "log in" in title_text:
            print("BLOCKED (auth wall) — LinkedIn requires login in this session")
            break

        # Public LinkedIn job search renders server-side cards
        cards = page.query_selector_all(
            "ul.jobs-search__results-list li, "
            "ul.base-search-page-list-container li"
        )
        new_count = 0

        for card in cards:
            try:
                title_el = (
                    card.query_selector("h3.base-search-card__title")
                    or card.query_selector("h3.job-search-card__title")
                )
                if not title_el:
                    continue
                title = title_el.inner_text().strip()

                company_el = (
                    card.query_selector("h4.base-search-card__subtitle")
                    or card.query_selector("a.job-search-card__company-name")
                )
                company = company_el.inner_text().strip() if company_el else "Unknown"

                # Skip US-location roles before dedup — covers the 93% geo-block failure mode
                location_el = (
                    card.query_selector("span.job-search-card__location")
                    or card.query_selector(".base-search-card__metadata span")
                )
                location = location_el.inner_text().strip() if location_el else ""
                if _is_us_location(location):
                    continue

                link_el = (
                    card.query_selector("a.base-card__full-link")
                    or card.query_selector("a.job-search-card__link-absolute")
                )
                href = (link_el.get_attribute("href") or "") if link_el else ""
                # Strip tracking params — everything after ?
                href = href.split("?")[0].rstrip("/")
                if not href or href in found_urls:
                    continue
                found_urls.add(href)

                job_id = f"linkedin:{url_id(href)}"
                if job_id in seen_ids:
                    continue
                seen_ids.add(job_id)

                matched = is_match(title, company)
                row = {
                    "job_id": job_id,
                    "company": company,
                    "title": title,
                    "url": href,
                    "found_date": today,
                    "matched": "yes" if matched else "no",
                    "source": "linkedin",
                }
                all_new.append(row)
                new_count += 1
                if matched:
                    matches.append(row)
            except Exception:
                continue

        print(f"{new_count} new")
        time.sleep(2)

    return all_new, matches


# ---------------------------------------------------------------------------
# Remote.co
# ---------------------------------------------------------------------------

def scrape_remoteco(page, seen_ids: set, today: str) -> tuple:
    all_new, matches = [], []

    url = "https://remote.co/remote-jobs/marketing/"
    print(f"    marketing listing ... ", end="", flush=True)

    try:
        page.goto(url, timeout=25000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
    except Exception as e:
        print(f"SKIP ({type(e).__name__})")
        return [], []

    # Remote.co uses WP Job Manager — cards are <li> inside .job_listings
    cards = page.query_selector_all(".job_listings li.job_listing")
    if not cards:
        cards = page.query_selector_all("li.job_listing")

    new_count = 0
    for card in cards:
        try:
            title_el = card.query_selector(".position h3, h3")
            if not title_el:
                continue
            title = title_el.inner_text().strip()

            company_el = card.query_selector(".company strong, .company_name")
            company = company_el.inner_text().strip() if company_el else "Unknown"

            link_el = card.query_selector("a")
            href = (link_el.get_attribute("href") or "") if link_el else ""
            if not href:
                continue
            if not href.startswith("http"):
                href = "https://remote.co" + href

            job_id = f"remoteco:{url_id(href)}"
            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            matched = is_match(title)
            row = {
                "job_id": job_id,
                "company": company,
                "title": title,
                "url": href,
                "found_date": today,
                "matched": "yes" if matched else "no",
                "source": "remoteco",
            }
            all_new.append(row)
            new_count += 1
            if matched:
                matches.append(row)
        except Exception:
            continue

    print(f"{new_count} new")
    return all_new, matches


# ---------------------------------------------------------------------------
# InfoJobs
# ---------------------------------------------------------------------------

def scrape_infojobs(page, seen_ids: set, today: str) -> tuple:
    all_new, matches = [], []
    found_urls: set = set()

    for query in INFOJOBS_QUERIES:
        q = query.replace(" ", "+")
        # teleworking=FULL_REMOTE = 100% remote filter; sortBy=PUBLICATION_DATE = newest first
        url = (
            f"https://www.infojobs.net/jobsearch/search-results/list.xhtml"
            f"?keyword={q}&teleworking=FULL_REMOTE&sortBy=PUBLICATION_DATE"
        )
        print(f"    {query!r} ... ", end="", flush=True)

        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
        except Exception as e:
            print(f"SKIP ({type(e).__name__})")
            continue

        body = page.content().lower()
        if "captcha" in body[:3000] or "access denied" in body[:3000] or "robot" in body[:3000]:
            print("BLOCKED — skipping InfoJobs for this run")
            break

        # InfoJobs renders offer cards as <li> items; try multiple selector patterns
        cards = page.query_selector_all(
            "li.ij-OfferCard, "
            "li[data-jobid], "
            "article.ij-OfferCard, "
            "ul#offerList li"
        )
        new_count = 0

        for card in cards:
            try:
                title_el = (
                    card.query_selector("h2 a")
                    or card.query_selector("a[class*='title']")
                    or card.query_selector("a[class*='Title']")
                    or card.query_selector("a[class*='offer']")
                )
                if not title_el:
                    continue
                title = title_el.inner_text().strip()
                if not title:
                    continue

                company_el = (
                    card.query_selector("a[class*='company']")
                    or card.query_selector("span[class*='company']")
                    or card.query_selector("[class*='Company']")
                    or card.query_selector("[class*='subtitle'] a")
                )
                company = company_el.inner_text().strip() if company_el else "Unknown"

                href = title_el.get_attribute("href") or ""
                if href.startswith("/"):
                    href = "https://www.infojobs.net" + href
                # Strip tracking params
                href = href.split("?")[0].rstrip("/")
                if not href or href in found_urls:
                    continue
                found_urls.add(href)

                job_id = f"infojobs:{url_id(href)}"
                if job_id in seen_ids:
                    continue
                seen_ids.add(job_id)

                matched = is_match(title, company)
                row = {
                    "job_id": job_id,
                    "company": company,
                    "title": title,
                    "url": href,
                    "found_date": today,
                    "matched": "yes" if matched else "no",
                    "source": "infojobs",
                }
                all_new.append(row)
                new_count += 1
                if matched:
                    matches.append(row)
            except Exception:
                continue

        print(f"{new_count} new")
        time.sleep(2)

    return all_new, matches


# ---------------------------------------------------------------------------
# Source registry
# ---------------------------------------------------------------------------

SOURCES = {
    "indeed":   scrape_indeed,
    "linkedin": scrape_linkedin,
    "remoteco": scrape_remoteco,
    "infojobs": scrape_infojobs,
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Print matches but don't write any files")
    parser.add_argument("--source", choices=list(SOURCES),
                        help="Run only this source (default: all)")
    args = parser.parse_args()

    today = date.today().isoformat()
    seen_ids = load_seen_ids()
    sources_to_run = {args.source: SOURCES[args.source]} if args.source else SOURCES

    all_new_seen: list = []
    all_matches: list = []

    chromium_exe = find_chromium_executable()

    with sync_playwright() as pw:
        launch_kwargs: dict = {
            "headless": True,
            "args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
        }
        if chromium_exe:
            launch_kwargs["executable_path"] = chromium_exe

        browser = pw.chromium.launch(**launch_kwargs)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        # Hide webdriver flag
        context.add_init_script("delete Object.getPrototypeOf(navigator).webdriver")
        page = context.new_page()

        for name, scraper in sources_to_run.items():
            print(f"\n[{name.upper()}]")
            try:
                new_seen, matches = scraper(page, seen_ids, today)
                all_new_seen.extend(new_seen)
                all_matches.extend(matches)
            except Exception as e:
                print(f"  ERROR: {e}")

        browser.close()

    # Write outputs
    new_matches = [r for r in all_new_seen if r["matched"] == "yes"]
    save_browser_finds(new_matches, dry_run=args.dry_run)
    append_to_csv(all_new_seen, dry_run=args.dry_run)

    if args.dry_run and all_new_seen:
        print(f"\n[dry-run] Would have recorded {len(all_new_seen)} jobs "
              f"({len(new_matches)} matches) to evaluated-jobs.csv and browser-finds.json")

    print()
    if not all_matches:
        print("No new matching roles found.")
        return

    print(f"{'=' * 62}")
    print(f"  BROWSER MATCHES  ({len(all_matches)} found — {today})")
    print(f"{'=' * 62}")
    for job in all_matches:
        print(f"\n{job['company']}: {job['title']}")
        print(f"  {job['url']}")
        print(f"  [via {job['source']}]")

    print(f"\n{'=' * 62}")
    print("Next: paste any posting above into /evaluate to score it.")
    print("      Then /tailor to generate tailored materials.")


if __name__ == "__main__":
    main()
