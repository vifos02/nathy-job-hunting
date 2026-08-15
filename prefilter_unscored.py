#!/usr/bin/env python3
"""
prefilter_unscored.py — Filter and rank all unscored matched jobs using
title/company rules from evaluate_matches.py. No web fetching required.
Optionally fetches Greenhouse JDs via public API for deeper hard-rule checks.

Run from the terminal in the nathy-job-hunting directory. No API credits needed.

Usage:
    python3 prefilter_unscored.py --csv ranked.csv          # rank + filter, no fetching
    python3 prefilter_unscored.py --write-skips --csv ranked.csv  # also tombstone clear SKIPs
    python3 prefilter_unscored.py --greenhouse --csv ranked.csv   # also fetch Greenhouse JDs
    python3 prefilter_unscored.py --dry-run                 # print count only
    python3 prefilter_unscored.py --limit 50                # process first N only

After running with --write-skips, evaluate_matches.py will skip the tombstoned
jobs and only score the survivors. Paste the top URLs from ranked.csv into
Claude Web (/evaluate) to score them for free.
"""

import argparse
import csv
import json
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
    HTTP_AVAILABLE = True
except ImportError:
    HTTP_AVAILABLE = False

ROOT            = Path(__file__).parent
SEEN_JOBS       = ROOT / "evaluated-jobs.csv"
BROWSER_FINDS   = ROOT / "browser-finds.json"
EVALS_DIR       = ROOT / "evaluations"
COMPANIES_MD    = ROOT / "companies.md"
MANUAL_REVIEWS  = ROOT / "manual-reviews.csv"

# ---------------------------------------------------------------------------
# Import filter rules from evaluate_matches.py (single source of truth)
# ---------------------------------------------------------------------------

sys.path.insert(0, str(ROOT))
try:
    from evaluate_matches import (
        REQUIRED_TITLE_KEYWORDS,
        SKIP_TITLE_WORDS,
        SKIP_INDUSTRY_WORDS,
        US_AUTH_TITLE_SIGNALS,
        US_ONLY_COMPANIES,
        BLOCKED_COMPANIES,
        MAX_AGE_DAYS,
        _kw_match,
    )
except ImportError as e:
    sys.exit(f"Could not import from evaluate_matches.py: {e}\nMake sure you're running from the nathy-job-hunting directory.")

# ---------------------------------------------------------------------------
# Tier 1 companies — get a relevancy boost
# ---------------------------------------------------------------------------

TIER1_COMPANIES = {
    "typeform", "factorial", "personio", "domestika", "semrush", "buffer",
    "hotmart", "rock content", "rockcontent", "ahrefs", "rd station", "rdstation",
    "totvs", "pipefy", "canva", "hubspot", "gitlab", "notion", "miro",
    "canonical", "contentsquare", "brevo", "mailchimp", "hootsuite",
}

# ---------------------------------------------------------------------------
# Closed-posting signals (for Greenhouse JD text check)
# ---------------------------------------------------------------------------

CLOSED_SIGNALS = [
    "no longer accepting", "this job is no longer", "position has been filled",
    "this position has been filled", "this role has been filled",
    "job is closed", "listing is closed", "posting is closed",
    "application period has closed", "no longer available",
    "listing has expired", "job expired", "not currently accepting",
    "vaga encerrada", "vaga expirada", "esta vaga não está mais disponível",
]

# Hard-blocker patterns to check in fetched JD text
ONSITE_SIGNALS = [
    "hybrid", "on-site", "on site", "in-office", "in office",
    "presencial", "escritório", "local de trabalho",
    "office-based", "must be based in", "work from our office",
    "híbrido", "trabalho presencial",
]
ONSITE_NEGATORS = [
    "not required", "not need", "no need", "optional", "flexible",
    "fully remote", "100% remote", "work from anywhere",
]
LANG_BARRIERS = [
    r"\bnative\s+(german|french|dutch|mandarin|chinese|japanese|korean)\b",
    r"\bfluent\s+(german|french|dutch|mandarin|chinese|japanese|korean)\b",
    r"\b(german|french|dutch)\s+language\s+required\b",
    r"\b(german|french|dutch)\s+speaker\b",
    r"\b(german|french|dutch)-speaking\b",
    r"\b(german|french|dutch)\s+(is\s+)?(a\s+)?(must|required|mandatory|essential)\b",
    r"\bc[12]\s+(german|french|dutch)\b",
]
US_AUTH_TEXT = [
    r"\bauthorized\s+to\s+work\s+in\s+the\s+(u\.?s\.?|united\s+states)\b",
    r"\bvisa\s+sponsorship\s+(is\s+)?not\s+(available|provided|offered)\b",
    r"\bno\s+visa\s+sponsorship\b",
    r"\bw-?2\s+only\b",
    r"\bmust\s+reside\s+in\s+the\s+(u\.?s\.?|united\s+states)\b",
]

# ---------------------------------------------------------------------------
# Load unscored matched jobs
# ---------------------------------------------------------------------------

def load_scored_ids() -> set:
    ids = set()
    for f in EVALS_DIR.glob("*.md"):
        m = re.search(r"<!-- job_id: (.+?) -->", f.read_text(encoding="utf-8"))
        if m:
            ids.add(m.group(1).strip())
    return ids


def load_manual_reviewed_ids() -> set:
    """Return job_ids that have been manually reviewed via mark_skip.py."""
    ids: set = set()
    if not MANUAL_REVIEWS.exists():
        return ids
    with MANUAL_REVIEWS.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("job_id"):
                ids.add(row["job_id"].strip())
    return ids


def load_unscored() -> list[dict]:
    scored = load_scored_ids()
    manual = load_manual_reviewed_ids()
    skip_ids = scored | manual
    rows = []
    seen_ids: set = set()

    if SEEN_JOBS.exists():
        with SEEN_JOBS.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("matched") == "yes" and row["job_id"] not in skip_ids:
                    if row["job_id"] not in seen_ids:
                        seen_ids.add(row["job_id"])
                        rows.append(row)

    if BROWSER_FINDS.exists():
        for entry in json.loads(BROWSER_FINDS.read_text(encoding="utf-8")):
            if entry.get("matched") == "yes" and entry["job_id"] not in skip_ids:
                if entry["job_id"] not in seen_ids:
                    seen_ids.add(entry["job_id"])
                    rows.append(entry)

    return rows

# ---------------------------------------------------------------------------
# LinkedIn domain allowlist — mirrors LINKEDIN_ALLOWED_SUBDOMAINS in browser_search.py.
# Jobs from any other *.linkedin.com subdomain are hard-blocked; almost all are
# on-site India/APAC/Middle East roles that survived the title-only pass.
# ---------------------------------------------------------------------------
LINKEDIN_ALLOWED_SUBDOMAINS = {
    "www",
    # LATAM
    "br", "mx", "co", "ar", "cl", "pe", "uy", "ec", "ve", "py", "bo",
    # Spain + Portugal
    "es", "pt",
    # UK + Ireland
    "uk", "ie",
    # Western + Northern Europe
    "de", "fr", "nl", "it", "be", "se", "no", "dk", "fi", "at", "ch", "lu",
    # North America
    "ca",
}

# ---------------------------------------------------------------------------
# Title + company hard filter (imported rules from evaluate_matches.py)
# ---------------------------------------------------------------------------

def title_company_filter(jobs: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Apply all title/company hard rules. Returns (survivors, eliminated).
    No web fetching — works from title and company name alone.
    """
    cutoff = date.today() - timedelta(days=MAX_AGE_DAYS)
    survivors, eliminated = [], []

    for job in jobs:
        title   = job.get("title", "").lower()
        company = job.get("company", "").lower()
        reason  = None

        # Age cutoff
        found_date_str = job.get("found_date", "")
        if found_date_str:
            try:
                if date.fromisoformat(found_date_str) < cutoff:
                    reason = f"too old ({found_date_str})"
            except ValueError:
                pass

        if reason is None:
            # LinkedIn domain check — reject non-target-market subdomains
            _url = job.get("url", "")
            _lm = re.match(r"https?://([a-z]{2,})\.linkedin\.com", _url)
            if _lm and _lm.group(1) not in LINKEDIN_ALLOWED_SUBDOMAINS:
                reason = f"LinkedIn domain not in target list: {_lm.group(1)}.linkedin.com"

        if reason is None:
            # Must match at least one target keyword
            if not any(_kw_match(kw, title) for kw in REQUIRED_TITLE_KEYWORDS):
                reason = "no target keyword in title"

        if reason is None:
            # Hard title blocklist
            for kw in SKIP_TITLE_WORDS:
                if kw in title:
                    reason = f"title blocker: '{kw}'"
                    break

        if reason is None:
            # Industry blocklist — check title AND company
            for kw in SKIP_INDUSTRY_WORDS:
                if kw in title or kw in company:
                    reason = f"industry blocker: '{kw}'"
                    break

        if reason is None:
            # US auth signals in title
            for kw in US_AUTH_TITLE_SIGNALS:
                if kw in title:
                    reason = f"US auth signal: '{kw}'"
                    break

        if reason is None:
            # US-only companies
            for co in US_ONLY_COMPANIES:
                if co in company:
                    reason = f"US-only company: '{co}'"
                    break

        if reason is None:
            # Blocked companies
            for co in BLOCKED_COMPANIES:
                if co in company:
                    reason = f"blocked company: '{co}'"
                    break

        if reason:
            eliminated.append({**job, "_reason": reason})
        else:
            survivors.append(job)

    return survivors, eliminated

# ---------------------------------------------------------------------------
# Relevancy score — title + company only, no JD text needed
# ---------------------------------------------------------------------------

# Strong positive title signals
REMOTE_TITLE_SIGNALS = ["remote", "remoto", "télétravail", "distributed"]
LATAM_TITLE_SIGNALS  = ["latam", "brazil", "brasil", "latin america", "portuguese", "spanish", "español"]
SENIORITY_SIGNALS    = ["senior", "sênior", "head", "director", "vp", "lead", "principal", "manager", "gerente", "diretor"]
CORE_SKILL_SIGNALS   = ["seo", "content", "growth", "demand gen", "digital marketing", "marketing manager",
                         "social media", "email marketing", "brand", "marketing specialist"]

# Positive URL signals (some job boards include remote in the URL)
REMOTE_URL_SIGNALS   = ["remote", "remoto", "work-from-home", "anywhere"]


def relevancy_score(job: dict) -> int:
    title   = job.get("title", "").lower()
    company = job.get("company", "").lower()
    url     = job.get("url", "").lower()
    score   = 0

    # Tier 1 company → big boost
    if any(t1 in company for t1 in TIER1_COMPANIES):
        score += 35

    # Remote signal in title
    if any(s in title for s in REMOTE_TITLE_SIGNALS):
        score += 25

    # Remote signal in URL
    if any(s in url for s in REMOTE_URL_SIGNALS):
        score += 10

    # LATAM / Brazil / language relevance in title
    latam_hits = sum(1 for s in LATAM_TITLE_SIGNALS if s in title)
    score += min(latam_hits * 10, 20)

    # Seniority match in title
    if any(s in title for s in SENIORITY_SIGNALS):
        score += 10

    # Core skill keywords in title
    skill_hits = sum(1 for s in CORE_SKILL_SIGNALS if s in title)
    score += min(skill_hits * 5, 15)

    # Greenhouse source = slightly higher company quality signal vs raw LinkedIn scrape
    if job.get("job_id", "").startswith("greenhouse:"):
        score += 5

    return min(score, 100)

# ---------------------------------------------------------------------------
# Optional: fetch Greenhouse JD via public API for deeper text checks
# ---------------------------------------------------------------------------

def fetch_greenhouse_jd(job_id: str) -> str:
    """Returns JD text or empty string on failure."""
    if not HTTP_AVAILABLE:
        return ""
    parts = job_id.split(":")
    if len(parts) != 3:
        return ""
    board, numeric_id = parts[1], parts[2]
    try:
        resp = requests.get(
            f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{numeric_id}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        if resp.status_code != 200:
            return ""
        data = resp.json()
        content_html = data.get("content", "")
        location     = data.get("location", {}).get("name", "")
        title        = data.get("title", "")
        text = BeautifulSoup(content_html, "html.parser").get_text(separator="\n", strip=True)
        return f"{title}\n{location}\n\n{text}"[:5000]
    except Exception:
        return ""


def check_jd_blockers(text: str) -> list[str]:
    reasons = []
    low = text.lower()

    if any(s in low for s in CLOSED_SIGNALS):
        return ["posting closed"]

    for signal in ONSITE_SIGNALS:
        if signal in low:
            idx = low.find(signal)
            ctx = low[max(0, idx - 60):idx]
            if not any(neg in ctx for neg in ONSITE_NEGATORS):
                reasons.append(f"on-site/hybrid: '{signal}'")
                break

    for pattern in LANG_BARRIERS:
        if re.search(pattern, low):
            reasons.append(f"language barrier: {pattern}")
            break

    for pattern in US_AUTH_TEXT:
        if re.search(pattern, low):
            reasons.append(f"US work auth required")
            break

    return reasons

# ---------------------------------------------------------------------------
# Write tombstone for confirmed SKIP
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def write_tombstone(job_id: str, company: str, title: str, url: str, reasons: list[str]) -> Path:
    EVALS_DIR.mkdir(exist_ok=True)
    filename = f"{date.today().isoformat()}-{slugify(company)}-{slugify(title)}.md"
    path = EVALS_DIR / filename
    # Avoid overwriting an existing real evaluation
    if path.exists():
        filename = f"{date.today().isoformat()}-{slugify(company)}-{slugify(title)}-pf.md"
        path = EVALS_DIR / filename
    reason_list = "\n".join(f"- {r}" for r in reasons)
    path.write_text(
        f"<!-- job_id: {job_id} -->\n"
        f"---\n"
        f"**{company} — {title}**\n"
        f"*Source: {url} | Evaluated: {date.today().isoformat()}*\n\n"
        f"**Verdict: SKIP** *(pre-filter — hard blocker, no Claude evaluation needed)*\n\n"
        f"**Hard blockers:**\n{reason_list}\n",
        encoding="utf-8",
    )
    return path

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", metavar="FILE",
                        help="Write ranked surviving candidates to a CSV file")
    parser.add_argument("--write-skips", action="store_true",
                        help="Write tombstone eval files for title-level hard-blocker SKIPs")
    parser.add_argument("--greenhouse", action="store_true",
                        help="Also fetch Greenhouse JDs via public API for deeper checks")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print count only, no output files")
    parser.add_argument("--limit", type=int, default=0,
                        help="Cap number of jobs processed (0 = no cap)")
    args = parser.parse_args()

    if args.greenhouse and not HTTP_AVAILABLE:
        sys.exit("requests/beautifulsoup4 not installed. Run: pip3 install requests beautifulsoup4")

    # Load all unscored jobs
    all_jobs = load_unscored()
    if not all_jobs:
        print("No unscored matched jobs found.")
        return

    if args.limit:
        all_jobs = all_jobs[:args.limit]

    total = len(all_jobs)
    print(f"\n{total} unscored matched jobs loaded.")

    if args.dry_run:
        print("Dry run — no output written.")
        return

    # Stage 1: apply title/company hard filters
    survivors, eliminated = title_company_filter(all_jobs)
    print(f"After title/company filter: {len(survivors)} survivors, {len(eliminated)} eliminated.")

    # Stage 2: optional Greenhouse JD fetch for deeper text checks
    jd_eliminated = []
    if args.greenhouse:
        gh_jobs = [j for j in survivors if j.get("job_id", "").startswith("greenhouse:")]
        print(f"Fetching {len(gh_jobs)} Greenhouse JDs for deeper checks...")
        still_alive = []
        for j in survivors:
            if j.get("job_id", "").startswith("greenhouse:"):
                text = fetch_greenhouse_jd(j["job_id"])
                if text:
                    blockers = check_jd_blockers(text)
                    if blockers:
                        jd_eliminated.append({**j, "_reason": "; ".join(blockers)})
                        print(f"  SKIP [{j['company']}]: {blockers[0]}")
                        continue
                    else:
                        print(f"  PASS [{j['company']}]")
                time.sleep(0.3)
            still_alive.append(j)
        survivors = still_alive
        print(f"After Greenhouse JD check: {len(survivors)} survivors, {len(jd_eliminated)} more eliminated.")

    # Stage 3: score and rank survivors
    for j in survivors:
        j["_score"] = relevancy_score(j)
    survivors.sort(key=lambda x: x["_score"], reverse=True)

    # Write tombstones for eliminated jobs
    if args.write_skips:
        tombstoned = 0
        for j in eliminated + jd_eliminated:
            write_tombstone(
                j["job_id"], j.get("company", ""), j.get("title", ""),
                j.get("url", ""), [j["_reason"]],
            )
            tombstoned += 1
        print(f"{tombstoned} tombstone eval files written to evaluations/")

    # Print ranked survivors
    print(f"\n{'='*65}")
    print(f"RANKED SURVIVORS — {len(survivors)} jobs (highest relevancy first)")
    print(f"{'='*65}\n")
    for rank, j in enumerate(survivors, 1):
        src = j.get("job_id", "").split(":")[0]
        print(f"  {rank:3}. [{j['_score']:3}/100] [{src}]")
        print(f"       {j.get('company','?')} — {j.get('title','?')}")
        print(f"       {j.get('url','')}")
        print()

    # Write CSV
    if args.csv:
        out = Path(args.csv)
        with out.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["rank", "relevancy", "company", "title", "url",
                             "found_date", "source", "job_id"])
            for rank, j in enumerate(survivors, 1):
                writer.writerow([
                    rank, j["_score"], j.get("company", ""), j.get("title", ""),
                    j.get("url", ""), j.get("found_date", ""),
                    j.get("source", ""), j.get("job_id", ""),
                ])
        print(f"Saved → {out}  ({len(survivors)} rows)")

    # Summary
    print(f"\nSummary:")
    print(f"  Loaded:     {total}")
    print(f"  Eliminated: {len(eliminated) + len(jd_eliminated)}  (title/company rules + JD checks)")
    print(f"  Survivors:  {len(survivors)}  (ranked in {args.csv or 'stdout'})")
    if args.write_skips:
        print(f"  Tombstoned: {len(eliminated) + len(jd_eliminated)}  (evaluate_matches.py will skip these)")
    print()
    if survivors:
        print(f"Next step: open ranked.csv and paste the top URLs into Claude Web → /evaluate")


if __name__ == "__main__":
    main()
