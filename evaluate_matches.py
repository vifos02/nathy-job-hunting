#!/usr/bin/env python3
"""
Auto-evaluator: reads new job matches, fetches posting content, scores each
via Claude API against Nathália's rubric, and saves results to evaluations/.

Run after scan_jobs.py and browser_search.py — integrated into run_scan.sh.

Requires:
    pip install anthropic requests beautifulsoup4
    export ANTHROPIC_API_KEY="sk-ant-..."   (add to ~/.zshrc or ~/.bash_profile)

Usage:
    python evaluate_matches.py              # evaluate up to 15 new matches
    python evaluate_matches.py --dry-run   # list candidates, no API calls
    python evaluate_matches.py --limit 5   # cap at N evaluations per run
"""

import argparse
import csv
import json
import os
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

try:
    import anthropic
except ImportError:
    sys.exit("Missing anthropic. Run: pip install anthropic")

ROOT          = Path(__file__).parent
CLAUDE_MD     = ROOT / "CLAUDE.md"
MASTER_RESUME = ROOT / "master-resume.md"
SEEN_JOBS     = ROOT / "evaluated-jobs.csv"
BROWSER_FINDS = ROOT / "browser-finds.json"
EVALS_DIR     = ROOT / "evaluations"

DEFAULT_LIMIT = 15

# Pre-filter: skip without calling the API
SKIP_TITLE_WORDS = [
    # Wrong level
    "junior", " jr ", "associate", "coordinator", "intern", "entry level",
    # Wrong function
    "developer", "engineer", "data scientist", "data analyst",
    "ppc specialist", "sem specialist", "paid search specialist",
    "product marketing",     # different discipline
    "lifecycle marketing",   # CRM/email focus, not her primary strength
    "account based",         # ABM, B2B ops
    "field marketing",       # events/in-person
    "event marketing",
    "enablement",            # sales enablement
    "demand generation",     # performance/paid focus
    "brand manager",         # brand-only, not digital
    "pr manager", "public relations",
    "influencer manager",
    "affiliate",
    # On-site locations in title
    "são paulo", "sao paulo",
    "tel aviv",
    "new york", "new york,",
    "san francisco",
    "austin,", "chicago,", "london,",
    "los angeles",
]

SKIP_INDUSTRY_WORDS = [
    "crypto", "cryptocurrency", "bitcoin", "blockchain",
    "betting", "gambling", "casino", "adult",
]

US_ONLY_TITLE_SIGNALS = [
    "remote us", "(us only)", "us-based", "north america only",
    "california", "us northeast", "us south", "us midwest",
]

US_ONLY_COMPANIES = {
    "spacex",
}


# ---------------------------------------------------------------------------
# Load context
# ---------------------------------------------------------------------------

def load_evaluated_ids() -> set:
    """Return job_ids that already have a saved evaluation file."""
    ids = set()
    for f in EVALS_DIR.glob("*.md"):
        for line in f.read_text(encoding="utf-8").split("\n")[:3]:
            if line.startswith("<!-- job_id:"):
                ids.add(line.replace("<!-- job_id:", "").replace("-->", "").strip())
    return ids


def load_new_matches(evaluated_ids: set) -> list[dict]:
    """Load matched rows from CSV + browser-finds that haven't been evaluated."""
    matches = []
    seen_urls: set = set()

    if SEEN_JOBS.exists():
        with SEEN_JOBS.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("matched") == "yes" and row["job_id"] not in evaluated_ids:
                    if row.get("url") not in seen_urls:
                        seen_urls.add(row.get("url", ""))
                        matches.append(row)

    if BROWSER_FINDS.exists():
        for entry in json.loads(BROWSER_FINDS.read_text(encoding="utf-8")):
            if entry.get("job_id") not in evaluated_ids:
                if entry.get("url") not in seen_urls:
                    seen_urls.add(entry.get("url", ""))
                    matches.append(entry)

    return matches


def prefilter(matches: list[dict]) -> list[dict]:
    """Apply hard exclusion rules without API calls."""
    keep = []
    for m in matches:
        title   = m.get("title", "").lower()
        company = m.get("company", "").lower()

        if any(kw in title for kw in SKIP_TITLE_WORDS):
            continue
        if any(kw in company for kw in SKIP_INDUSTRY_WORDS):
            continue
        if any(kw in title for kw in US_ONLY_TITLE_SIGNALS):
            continue
        if any(co in company for co in US_ONLY_COMPANIES):
            continue

        keep.append(m)
    return keep


# ---------------------------------------------------------------------------
# Fetch posting content
# ---------------------------------------------------------------------------

def fetch_posting(url: str) -> str:
    """Fetch and extract readable text from a job posting URL."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.content, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return text[:8000]
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Evaluate via Claude API
# ---------------------------------------------------------------------------

def evaluate_with_claude(client: anthropic.Anthropic, company: str, title: str,
                          url: str, posting_text: str,
                          rubric: str, resume: str) -> str:
    if posting_text:
        posting_block = f"FULL POSTING TEXT:\n{posting_text}"
    else:
        posting_block = (
            "[Posting content could not be fetched — LinkedIn or site blocked the request. "
            "Score based on company reputation and title only. Note this limitation clearly.]"
        )

    prompt = f"""You are scoring a job posting for Nathália Follmann against her scoring rubric.
Be honest. Do not inflate scores. A 5/10 or 6/10 is fine if that is the truth.

=== RUBRIC, HARD RULES, AND CONTEXT ===
{rubric}

=== HER DOCUMENTED SKILLS AND EXPERIENCE (source of truth — never invent) ===
{resume}

=== JOB TO EVALUATE ===
Company: {company}
Title: {title}
URL: {url}

{posting_block}

=== OUTPUT (follow this format exactly, fill every cell) ===
---
**{company} — {title}**
*Source: {url} | Evaluated: {date.today().isoformat()}*

| Dimension | Score | Reasoning |
|-----------|-------|-----------|
| Role Fit (30%) | X/10 | |
| Remote / Location (25%) | X/10 | |
| Compensation (20%) | X/10 | |
| Company Quality (15%) | X/10 | |
| Skill Match (10%) | X/10 | |
| **Final Score** | **X.X/10** | *(Role×0.30)+(Remote×0.25)+(Comp×0.20)+(Co×0.15)+(Skills×0.10)* |

**Verdict: APPLY / CONSIDER / SKIP**

**Top 3 Reasons to Apply**
1.
2.
3.

**Top 3 Concerns (be honest)**
1.
2.
3.

**Most Relevant Resume Bullets to Lead With**
-

**Hard Dealbreakers Present?**
- [ ] EU work permit required
- [ ] On-site in city she doesn't live in
- [ ] BRL-only pay below R$15k/month
- [ ] US-remote only
- Others (list any):
---"""

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", text.lower())
    return text.strip("-")[:40]


def save_evaluation(job_id: str, company: str, title: str, content: str) -> Path:
    EVALS_DIR.mkdir(exist_ok=True)
    filename = f"{date.today().isoformat()}-{slugify(company)}-{slugify(title)}.md"
    path = EVALS_DIR / filename
    path.write_text(f"<!-- job_id: {job_id} -->\n{content}", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="List candidates without calling API")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                        help=f"Max evaluations per run (default: {DEFAULT_LIMIT})")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        sys.exit("ANTHROPIC_API_KEY not set.\nRun: export ANTHROPIC_API_KEY='sk-ant-...'")

    rubric = CLAUDE_MD.read_text(encoding="utf-8")     if CLAUDE_MD.exists()     else ""
    resume = MASTER_RESUME.read_text(encoding="utf-8") if MASTER_RESUME.exists() else ""

    evaluated_ids = load_evaluated_ids()
    matches       = load_new_matches(evaluated_ids)
    matches       = prefilter(matches)

    if not matches:
        print("No new matches to evaluate.")
        return

    total = len(matches)
    cap   = args.limit
    print(f"{total} candidates after pre-filtering. "
          f"{'Dry run.' if args.dry_run else f'Evaluating up to {cap}.'}\n")

    if args.dry_run:
        for m in matches[:cap]:
            print(f"  {m['company']}: {m['title']}")
            print(f"    {m['url']}")
        if total > cap:
            print(f"  ... and {total - cap} more")
        return

    client    = anthropic.Anthropic(api_key=api_key)
    evaluated = 0

    for m in matches:
        if evaluated >= cap:
            remaining = total - evaluated
            print(f"\nLimit of {cap} reached ({remaining} remaining). "
                  f"Run again or increase --limit.")
            break

        company = m.get("company", "Unknown")
        title   = m.get("title", "Unknown")
        url     = m.get("url", "")
        job_id  = m.get("job_id", f"noid-{slugify(company)}-{slugify(title)}")

        print(f"  [{evaluated + 1}/{min(cap, total)}] {company} — {title}")
        print(f"    Fetching posting ... ", end="", flush=True)
        posting_text = fetch_posting(url)
        print("ok" if posting_text else "blocked (will score from title/company)")

        print(f"    Scoring ... ", end="", flush=True)
        try:
            result = evaluate_with_claude(
                client, company, title, url, posting_text, rubric, resume
            )
            path = save_evaluation(job_id, company, title, result)
            print(f"saved → {path.name}")
            evaluated += 1
        except Exception as e:
            print(f"ERROR: {e}")

        time.sleep(0.5)

    print(f"\n{evaluated} evaluation(s) saved to evaluations/")
    print("Run /digest to see scored results and priority list.")


if __name__ == "__main__":
    main()
