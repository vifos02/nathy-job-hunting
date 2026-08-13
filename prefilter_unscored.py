#!/usr/bin/env python3
"""
prefilter_unscored.py — Fetch JDs for all unscored matched jobs, apply
hard-rule filters from the posting text, rank survivors by relevancy, and
optionally write tombstone eval files for confirmed SKIPs so evaluate_matches.py
never wastes API credits on them.

No Claude API calls. Run this locally on your Mac — LinkedIn and Greenhouse
both need a real browser or API; they block plain HTTP requests in the cloud.

Fetch strategies used automatically by source:
  greenhouse:*  → Greenhouse public JSON API (no login needed)
  linkedin:*    → Playwright with your logged-in browser (requires --playwright)
  others        → plain requests + BeautifulSoup

Usage:
    python prefilter_unscored.py                     # fetch + filter + print ranked list
    python prefilter_unscored.py --playwright        # use Playwright for LinkedIn JDs
    python prefilter_unscored.py --write-skips       # also write tombstone eval files
    python prefilter_unscored.py --csv ranked.csv    # save survivors to CSV
    python prefilter_unscored.py --dry-run           # show list, no fetching
    python prefilter_unscored.py --limit 50          # process only first N jobs

Recommended first run:
    python prefilter_unscored.py --playwright --write-skips --csv ranked.csv

After running with --write-skips, evaluate_matches.py will skip the confirmed SKIPs
and only score the survivors.
"""

import argparse
import csv
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("Missing dependencies. Run: pip install requests beautifulsoup4")

# Playwright is optional — only needed for LinkedIn URLs
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

ROOT        = Path(__file__).parent
SEEN_JOBS   = ROOT / "evaluated-jobs.csv"
BROWSER_FINDS = ROOT / "browser-finds.json"
EVALS_DIR   = ROOT / "evaluations"

# ---------------------------------------------------------------------------
# Load unscored matched jobs (same dedup logic as list_unscored.py)
# ---------------------------------------------------------------------------

def load_scored_ids() -> set:
    ids = set()
    for f in EVALS_DIR.glob("*.md"):
        m = re.search(r"<!-- job_id: (.+?) -->", f.read_text(encoding="utf-8"))
        if m:
            ids.add(m.group(1).strip())
    return ids


def load_unscored() -> list[dict]:
    scored = load_scored_ids()
    rows = []
    seen_ids: set = set()

    if SEEN_JOBS.exists():
        with SEEN_JOBS.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("matched") == "yes" and row["job_id"] not in scored:
                    if row["job_id"] not in seen_ids:
                        seen_ids.add(row["job_id"])
                        rows.append(row)

    if BROWSER_FINDS.exists():
        for entry in json.loads(BROWSER_FINDS.read_text(encoding="utf-8")):
            if entry.get("matched") == "yes" and entry["job_id"] not in scored:
                if entry["job_id"] not in seen_ids:
                    seen_ids.add(entry["job_id"])
                    rows.append(entry)

    return rows


# ---------------------------------------------------------------------------
# Fetch posting (no Claude) — three strategies by source
# ---------------------------------------------------------------------------

CLOSED_SIGNALS = [
    "no longer accepting", "this job is no longer", "position has been filled",
    "this position has been filled", "this role has been filled",
    "job is closed", "listing is closed", "posting is closed",
    "application period has closed", "no longer available",
    "listing has expired", "job expired", "expired job",
    "not currently accepting", "applications are closed",
    "vaga encerrada", "vaga expirada", "esta vaga não está mais disponível",
]

_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8",
}


def _text_from_html(html_bytes: bytes) -> str:
    soup = BeautifulSoup(html_bytes, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def _check_closed(text: str) -> bool:
    low = text.lower()
    return any(s in low for s in CLOSED_SIGNALS)


def fetch_greenhouse(job_id: str) -> str | None:
    """Use Greenhouse public JSON API — no login, no JS rendering needed."""
    # job_id format: greenhouse:<board>:<numeric_id>
    parts = job_id.split(":")
    if len(parts) != 3:
        return ""
    board, numeric_id = parts[1], parts[2]
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{numeric_id}"
    try:
        resp = requests.get(api_url, headers=_HTTP_HEADERS, timeout=15)
        if resp.status_code in (404, 410):
            return None
        if resp.status_code != 200:
            return ""
        data = resp.json()
        # Extract title, location, and content (HTML) from JSON
        title    = data.get("title", "")
        location = data.get("location", {}).get("name", "")
        content_html = data.get("content", "")
        # Strip HTML from content field
        content_text = BeautifulSoup(content_html, "html.parser").get_text(separator="\n", strip=True)
        full = f"{title}\n{location}\n\n{content_text}"
        if _check_closed(full):
            return None
        if len(full.strip()) < 100:
            return ""
        return full[:6000]
    except Exception:
        return ""


def fetch_via_playwright(url: str, pw_page) -> str | None:
    """Fetch a JS-rendered page using an already-open Playwright page."""
    try:
        pw_page.goto(url, wait_until="domcontentloaded", timeout=20_000)
        pw_page.wait_for_timeout(2000)  # let JS hydrate
        content = pw_page.content()
        text = _text_from_html(content.encode())
        if _check_closed(text):
            return None
        if len(text.strip()) < 200:
            return ""
        return text[:6000]
    except Exception:
        return ""


def fetch_plain_http(url: str) -> str | None:
    """Plain requests fetch — works for ATS boards that serve static HTML."""
    try:
        resp = requests.get(url, headers=_HTTP_HEADERS, timeout=15, allow_redirects=True)
        if resp.status_code in (403, 404, 410):
            return None
        if resp.status_code != 200:
            return ""
        text = _text_from_html(resp.content)
        if _check_closed(text):
            return None
        if len(text.strip()) < 200:
            return ""
        return text[:6000]
    except Exception:
        return ""


def fetch_jd(job: dict, pw_page=None) -> str | None:
    """
    Route to the right fetch strategy based on job_id source prefix.
    Returns:
      None → dead URL or confirmed closed
      ""   → blocked (login/JS wall) — rule-check skipped
      str  → posting text (up to 6000 chars)
    """
    job_id = job.get("job_id", "")
    url    = job.get("url", "")

    if job_id.startswith("greenhouse:"):
        return fetch_greenhouse(job_id)

    if job_id.startswith("linkedin:"):
        if pw_page is not None:
            return fetch_via_playwright(url, pw_page)
        return ""  # can't fetch without Playwright — pass through as blocked

    return fetch_plain_http(url)


# ---------------------------------------------------------------------------
# Hard-rule text checks — returns reason string or None
# ---------------------------------------------------------------------------

# Hybrid / on-site confirmed
ONSITE_SIGNALS = [
    "hybrid", "on-site", "on site", "in-office", "in office",
    "presencial", "escritório", "local de trabalho",
    "office-based", "must be based in", "work from our office",
    "work from the office", "required to be in",
    "híbrido", "trabalho presencial",
]
# Phrases that neutralise an on-site signal (e.g. "not required to be on-site")
ONSITE_NEGATORS = [
    "not required", "not need", "no need", "optional", "flexible",
    "fully remote", "100% remote", "work from anywhere",
]

# Language requirements — languages she doesn't speak professionally
LANG_BARRIERS = [
    # German
    r"\bnative\s+german\b", r"\bfluent\s+german\b", r"\bgerman\s+language\s+required\b",
    r"\bgerman\s+speaker\b", r"\bgerman-speaking\b", r"\bprofessional\s+german\b",
    r"\bgerman\s+proficiency\b", r"\bc2\s+german\b", r"\bc1\s+german\b",
    r"\bgerman\s+(is\s+)?(a\s+)?(must|required|mandatory|essential)\b",
    # French
    r"\bnative\s+french\b", r"\bfluent\s+french\b", r"\bfrench\s+language\s+required\b",
    r"\bfrench\s+speaker\b", r"\bfrench-speaking\b", r"\bprofessional\s+french\b",
    r"\bfrench\s+proficiency\b", r"\bc2\s+french\b", r"\bc1\s+french\b",
    r"\bfrench\s+(is\s+)?(a\s+)?(must|required|mandatory|essential)\b",
    # Dutch
    r"\bnative\s+dutch\b", r"\bfluent\s+dutch\b", r"\bdutch\s+language\s+required\b",
    r"\bdutch\s+speaker\b", r"\bdutch-speaking\b", r"\bprofessional\s+dutch\b",
    r"\bdutch\s+proficiency\b", r"\bc2\s+dutch\b", r"\bc1\s+dutch\b",
    r"\bdutch\s+(is\s+)?(a\s+)?(must|required|mandatory|essential)\b",
    # Mandarin / Japanese / Korean (not in her profile)
    r"\bnative\s+(mandarin|chinese|japanese|korean)\b",
    r"\bfluent\s+(mandarin|chinese|japanese|korean)\b",
    r"\b(mandarin|japanese|korean)\s+(language\s+)?(is\s+)?(a\s+)?(must|required|mandatory)\b",
]

# US work authorisation signals
US_AUTH_SIGNALS = [
    r"\bauthorized\s+to\s+work\s+in\s+the\s+(u\.?s\.?|united\s+states)\b",
    r"\bwork\s+authorization\s+in\s+the\s+(u\.?s\.?|united\s+states)\b",
    r"\bmust\s+be\s+(legally\s+)?eligible\s+to\s+work\s+in\s+the\s+(u\.?s\.?|united\s+states)\b",
    r"\b(us|u\.s\.)\s+citizen(ship)?\s+required\b",
    r"\bvisa\s+sponsorship\s+(is\s+)?(not\s+)?(available|provided|offered)\b",
    r"\bwe\s+(do\s+not|don'?t|cannot|can'?t)\s+(offer|provide)\s+visa\s+sponsorship\b",
    r"\bno\s+visa\s+sponsorship\b",
    r"\bw-?2\s+only\b",
    r"\bmust\s+reside\s+in\s+the\s+(u\.?s\.?|united\s+states)\b",
    r"\bbased\s+in\s+the\s+(u\.?s\.?|united\s+states)\s+required\b",
]

# Low-salary signals — disclosed salary clearly below target (€/$/£ < ~35k annual or <$15/hr)
LOW_SALARY_PATTERNS = [
    # Annual ranges — catches "£25,000", "$30,000–$40,000", "R$10.000", etc.
    r"(?:£|€|\$|r\$)\s*(\d{1,3}(?:[,\.]\d{3})*)\s*(?:–|-|to|a)\s*(?:£|€|\$|r\$)?\s*(\d{1,3}(?:[,\.]\d{3})*)",
]
# Target floor in each currency (annual gross)
SALARY_FLOORS = {
    "£": 35_000,
    "€": 40_000,
    "$": 45_000,
    "r$": 60_000,   # R$ ~BRL — floor ~R$5k/month
}


def _parse_salary_number(raw: str) -> int:
    """Turn '45,000' or '45.000' into 45000."""
    return int(re.sub(r"[,\.]", "", raw))


def check_hard_blockers(text: str) -> list[str]:
    """Return list of confirmed blocker reasons found in JD text. Empty = none found."""
    reasons = []
    low = text.lower()

    # 1. Hybrid / on-site
    for signal in ONSITE_SIGNALS:
        if signal in low:
            # Check if a negator appears within 60 chars before the signal
            idx = low.find(signal)
            context_before = low[max(0, idx - 60):idx]
            if not any(neg in context_before for neg in ONSITE_NEGATORS):
                reasons.append(f"on-site/hybrid: '{signal}' found in JD")
                break

    # 2. Language barriers
    for pattern in LANG_BARRIERS:
        if re.search(pattern, low):
            reasons.append(f"language barrier: matched /{pattern}/")
            break

    # 3. US work auth
    for pattern in US_AUTH_SIGNALS:
        if re.search(pattern, low):
            reasons.append(f"US work auth required: matched /{pattern}/")
            break

    # 4. Disclosed low salary
    for pattern in LOW_SALARY_PATTERNS:
        for m in re.finditer(pattern, low):
            currency_raw = m.group(0)[0:3].strip().replace(" ", "")
            # Identify currency symbol
            currency = None
            for sym in SALARY_FLOORS:
                if currency_raw.startswith(sym) or m.group(0).startswith(sym):
                    currency = sym
                    break
            if currency is None:
                # Try to find currency at start of full match
                full = m.group(0)
                for sym in SALARY_FLOORS:
                    if sym in full[:4].lower():
                        currency = sym
                        break
            if currency is None:
                continue
            try:
                high = _parse_salary_number(m.group(2))
                if high < SALARY_FLOORS[currency]:
                    reasons.append(
                        f"salary below target: {m.group(0).strip()} (floor {currency}{SALARY_FLOORS[currency]:,})"
                    )
                    break
            except (IndexError, ValueError):
                pass

    return reasons


# ---------------------------------------------------------------------------
# Relevancy heuristic (no Claude)
# Scores 0–100; higher = more likely to pass full evaluation.
# This is approximate — it helps prioritise, not filter.
# ---------------------------------------------------------------------------

# Remote-positive signals in JD text
REMOTE_SIGNALS = [
    "fully remote", "100% remote", "work from anywhere", "remote-first",
    "remote first", "anywhere in the world", "globally distributed",
    "distributed team", "fully distributed", "remote ok", "remote friendly",
    "open to remote", "remote position", "remote role", "remote work",
    "trabalho remoto", "100% remoto", "totalmente remoto",
    "trabajo remoto", "100% remoto", "completamente remoto",
]
# LATAM / Brazil positive signals
LATAM_SIGNALS = [
    "latam", "latin america", "brazil", "brasil", "são paulo", "sao paulo",
    "portuguese", "español", "spanish", "bilingual",
]
# Seniority signals (she's senior — these are positive)
SENIORITY_SIGNALS = [
    "senior", "manager", "director", "head of", "lead", "principal",
    "staff", "vp", "vice president", "sênior", "gerente", "diretor",
]
# Core skill signals
SKILL_SIGNALS = [
    "seo", "content", "growth", "demand generation", "digital marketing",
    "social media", "marketing manager", "marketing strategy",
    "email marketing", "brand", "analytics", "campaign",
]
# Good-industry signals
INDUSTRY_SIGNALS = [
    "saas", "software", "technology", "tech", "fintech", "startup",
    "scale-up", "scaleup", "series", "funded", "remote-first",
    "platform", "product-led", "plg",
]


def relevancy_score(title: str, company: str, text: str) -> int:
    low_title = title.lower()
    low_text  = (text or "").lower()
    score = 0

    # Remote signal in JD text — biggest positive factor
    for sig in REMOTE_SIGNALS:
        if sig in low_text:
            score += 30
            break

    # LATAM / Brazil relevance
    latam_hits = sum(1 for s in LATAM_SIGNALS if s in low_text or s in low_title)
    score += min(latam_hits * 8, 20)

    # Core skill density in JD
    skill_hits = sum(1 for s in SKILL_SIGNALS if s in low_text)
    score += min(skill_hits * 3, 15)

    # Seniority in title
    if any(s in low_title for s in SENIORITY_SIGNALS):
        score += 10

    # Good-industry signals
    if any(s in low_text for s in INDUSTRY_SIGNALS):
        score += 8

    # Fully remote in title itself
    if "remote" in low_title:
        score += 10

    # Penalty: vague job description (JD was blocked/empty)
    if not text:
        score = max(score - 15, 0)

    return min(score, 100)


# ---------------------------------------------------------------------------
# Write tombstone evaluation file for confirmed SKIP
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def write_tombstone(job_id: str, company: str, title: str, url: str, reasons: list[str]) -> Path:
    EVALS_DIR.mkdir(exist_ok=True)
    filename = f"{date.today().isoformat()}-{slugify(company)}-{slugify(title)}.md"
    path = EVALS_DIR / filename
    reason_list = "\n".join(f"- {r}" for r in reasons)
    content = (
        f"<!-- job_id: {job_id} -->\n"
        f"---\n"
        f"**{company} — {title}**\n"
        f"*Source: {url} | Evaluated: {date.today().isoformat()}*\n\n"
        f"**Verdict: SKIP** *(pre-filter — hard blocker confirmed in JD text, no Claude evaluation needed)*\n\n"
        f"**Hard blockers found:**\n{reason_list}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="Show unscored list without fetching any URLs")
    parser.add_argument("--playwright", action="store_true",
                        help="Use Playwright to fetch LinkedIn JDs (requires: pip install playwright && playwright install chromium)")
    parser.add_argument("--write-skips", action="store_true",
                        help="Write tombstone eval files for confirmed hard-blocker SKIPs")
    parser.add_argument("--csv", metavar="FILE",
                        help="Write ranked surviving candidates to CSV file")
    parser.add_argument("--limit", type=int, default=0,
                        help="Cap number of jobs fetched (0 = no cap)")
    args = parser.parse_args()

    if args.playwright and not PLAYWRIGHT_AVAILABLE:
        sys.exit("Playwright not installed. Run: pip install playwright && playwright install chromium")

    jobs = load_unscored()
    if not jobs:
        print("No unscored matched jobs found.")
        return

    if args.limit:
        jobs = jobs[:args.limit]

    total = len(jobs)
    linkedin_count = sum(1 for j in jobs if j.get("job_id", "").startswith("linkedin:"))
    greenhouse_count = sum(1 for j in jobs if j.get("job_id", "").startswith("greenhouse:"))
    print(f"\n{total} unscored matched jobs to process.")
    print(f"  Greenhouse (JSON API): {greenhouse_count}")
    print(f"  LinkedIn (Playwright): {linkedin_count}" + (" — will use Playwright" if args.playwright else " — JDs blocked without --playwright"))
    print(f"  Other: {total - linkedin_count - greenhouse_count}\n")

    if args.dry_run:
        for i, j in enumerate(jobs, 1):
            print(f"  {i:3}. {j['company']} — {j['title']}")
            print(f"       {j['url']}")
        return

    skipped   = []   # confirmed hard blocker
    dead      = []   # 404/closed URL
    survivors = []   # passed all hard rules

    # Start Playwright once for all LinkedIn URLs if requested
    pw_context = None
    pw_page    = None
    pw_inst    = None

    if args.playwright:
        print("Starting Playwright browser for LinkedIn fetches...")
        pw_inst = sync_playwright().start()
        browser = pw_inst.chromium.launch(headless=True)
        pw_context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        pw_page = pw_context.new_page()
        print("Browser ready.\n")

    try:
        for i, job in enumerate(jobs, 1):
            company = job.get("company", "Unknown")
            title   = job.get("title", "Unknown")
            url     = job.get("url", "")
            job_id  = job.get("job_id", f"noid-{i}")
            source  = job_id.split(":")[0]

            print(f"  [{i:3}/{total}] [{source}] {company} — {title}")

            text = fetch_jd(job, pw_page=pw_page)

            if text is None:
                print(f"           → DEAD/CLOSED URL")
                dead.append({**job, "_reason": "dead/closed URL"})
                if args.write_skips:
                    write_tombstone(job_id, company, title, url, ["Dead or closed URL (4xx / posting says no longer accepting)"])
                time.sleep(0.3)
                continue

            if text == "":
                print(f"           → BLOCKED (no JD text) — passing through")
                rscore = relevancy_score(title, company, "")
                survivors.append({**job, "_text": "", "_relevancy": rscore, "_note": "JD blocked"})
                time.sleep(0.3)
                continue

            blockers = check_hard_blockers(text)
            if blockers:
                reason_str = "; ".join(blockers)
                print(f"           → SKIP — {reason_str}")
                skipped.append({**job, "_reason": reason_str})
                if args.write_skips:
                    path = write_tombstone(job_id, company, title, url, blockers)
                    print(f"              tombstone → {path.name}")
            else:
                rscore = relevancy_score(title, company, text)
                print(f"           → PASS (relevancy {rscore}/100)")
                survivors.append({**job, "_text": text[:300], "_relevancy": rscore, "_note": ""})

            time.sleep(0.4)  # polite crawl delay

    finally:
        if pw_inst:
            pw_inst.stop()

    # Sort survivors by relevancy descending
    survivors.sort(key=lambda x: x["_relevancy"], reverse=True)

    # Summary
    print(f"\n{'='*65}")
    print(f"RESULTS — {total} jobs processed")
    print(f"  SKIP (hard blocker in JD):  {len(skipped):3}")
    print(f"  Dead/closed URL:            {len(dead):3}")
    blocked_count = sum(1 for s in survivors if s.get("_note") == "JD blocked")
    print(f"  Blocked (JD not readable):  {blocked_count:3}")
    print(f"  SURVIVORS (worth scoring):  {len(survivors):3}")
    print(f"{'='*65}\n")

    if survivors:
        print("RANKED SURVIVORS (highest relevancy first):\n")
        for rank, s in enumerate(survivors, 1):
            note = f"  [{s['_note']}]" if s.get("_note") else ""
            print(f"  {rank:3}. [{s['_relevancy']:3}/100]{note}")
            print(f"       {s['company']} — {s['title']}")
            print(f"       {s['url']}")
            print()

    if args.csv and survivors:
        out = Path(args.csv)
        with out.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["rank", "relevancy", "company", "title", "url",
                              "found_date", "source", "job_id", "note"])
            for rank, s in enumerate(survivors, 1):
                writer.writerow([
                    rank, s["_relevancy"], s["company"], s["title"],
                    s["url"], s.get("found_date", ""), s.get("source", ""),
                    s["job_id"], s.get("_note", ""),
                ])
        print(f"Saved ranked list → {out}")

    if args.write_skips and (skipped or dead):
        print(f"\n{len(skipped) + len(dead)} tombstone eval files written to evaluations/")
        print("Run evaluate_matches.py to score the remaining survivors.")
    elif survivors:
        print("Re-run with --write-skips to record the SKIPs and free up slots in evaluate_matches.py.")


if __name__ == "__main__":
    main()
