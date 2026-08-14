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
from datetime import date, timedelta
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

MAX_AGE_DAYS = 7

# Allowlist: title must contain at least one of these to pass to the API.
# Keeps only the roles that genuinely match Nathália's target disciplines.
REQUIRED_TITLE_KEYWORDS = [
    "seo",
    "search engine optimization",
    "content marketing",
    "content manager",
    "content director",
    "content strategist",
    "content lead",
    "content specialist",
    "digital marketing",
    "growth marketing",
    "growth manager",
    "marketing operations",
    "marketing manager",
    "marketing director",
    "marketing specialist",
    "marketing project manager",
    "marketing program manager",
    "head of marketing",
    "head of content",
    "head of seo",
    "vp marketing",
    "vp of marketing",
    "vp, marketing",
    "latam marketing",
    "latam content",
    "latam seo",
    "social media marketing",
    "demand generation",
    # Portuguese-language equivalents — surfaces Brazilian boards (Gupy, LinkedIn BR) in PT
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
    "coordenador sênior de marketing",
    # Spanish-language equivalents — LATAM boards
    "director de marketing",
    "directora de marketing",
    "jefe de marketing",
    "jefa de marketing",
    "responsable de marketing",
    "responsable seo",
    "especialista en seo",
    "especialista en marketing",
    "especialista en marketing digital",
]

# Hard blocklist: skip even if an allowlist keyword matched
SKIP_TITLE_WORDS = [
    "junior", " jr ", "associate", "coordinator", "intern", "entry level",
    "developer", "engineer", "data scientist", "data analyst",
    "ppc specialist", "sem specialist", "paid search specialist",
    ", sem",  # e.g. "Growth Marketing Lead, SEM"
    "product marketing",
    "lifecycle marketing",
    "account based",
    "field marketing",
    "event marketing",
    "enablement",
    "affiliate",
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
    # APAC / non-workable locations in title
    "japan", "tokyo", "singapore", "apac", "asia pacific",
    "china", "hong kong", "korea", "sydney", "australia",
    "indonesia", "jakarta", "malaysia", "kuala lumpur", "philippines",
    # DACH = Germany/Austria/Switzerland region; requires German fluency she doesn't have
    "dach",
    # On-site locations in title — cities she won't be near
    # São Paulo and Curitiba are intentionally NOT blocked — moving to Brazil Nov 2026,
    # hybrid roles there are in scope.
    "tel aviv",
    "new york,", "san francisco,", "austin,", "chicago,", "los angeles,",
    "seattle,", "boston,", "denver,", "miami,", "atlanta,",
    # E-commerce as job function (not company industry) — outside target scope
    "e-commerce", "ecommerce", "e commerce", "e-comm",
    "comércio eletrônico",
    # CRM as primary job function — specialist/ops discipline outside target scope
    "crm",
    # On-site role types that rarely go remote
    "office manager",
    # Portuguese-language blocklist — junior/entry-level titles in PT
    "coordenador de marketing", "coordenadora de marketing",
    "assistente de marketing", "estagiário", "estagiária", "júnior",
    # Language-requirement signals in title — languages she doesn't speak professionally.
    # "— German" / "- French" at end of title = language required, not location.
    # "germany" / "france" are NOT blocked here (location tag, not language requirement).
    # Portuguese and Spanish are NOT blocked (native / fluent).
    "— german", "- german", "(german)", "| german",
    "german language", "german speaker", "german-speaking", "native german",
    "— french", "- french", "(french)", "| french",
    "french language", "french speaker", "french-speaking", "native french",
    "— dutch", "- dutch", "(dutch)", "| dutch",
    "dutch language", "dutch speaker", "dutch-speaking", "native dutch",
]

SKIP_INDUSTRY_WORDS = [
    "crypto", "cryptocurrency", "bitcoin", "blockchain",
    "betting", "gambling", "casino",
    "igaming", "i-gaming",
    "nft", "defi", "web3", "dao",
    "adult entertainment", "adult content",
]

# Title signals that explicitly restrict to US applicants (work authorization implied)
# Note: timezone signals like "east coast hours" or "us remote" alone are NOT blockers —
# Brazil (UTC-3) is compatible with US East Coast. Only skip if authorization is clearly required.
US_AUTH_TITLE_SIGNALS = [
    "(us only)", "us citizens only", "us citizenship required",
    "must be authorized to work in the us",
    # US city names with comma (indicating on-site, not remote)
    "california,", "us northeast,", "us south,", "us midwest,",
]

US_ONLY_COMPANIES = {
    "spacex",
}

# Companies confirmed to operate in blocked industries (crypto, betting, gambling, adult)
# that have neutral-sounding names the SKIP_INDUSTRY_WORDS filter won't catch.
BLOCKED_COMPANIES = {
    "north star network",  # sports betting media
    "sui foundation",      # crypto
    "rubyplay",            # casino games
    "odds scanner group",  # sports betting
    "redcore",             # iGaming/gambling SEO niche
    "aphex media",         # iGaming SEO agency
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


def _company_title_key(row: dict) -> str:
    """Normalised key for cross-platform dedup (same role posted on LinkedIn + ATS)."""
    c = re.sub(r"[^a-z0-9]", "", row.get("company", "").lower())
    t = re.sub(r"[^a-z0-9]", "", row.get("title", "").lower())
    return f"{c}|{t}"


def load_new_matches(evaluated_ids: set) -> list[dict]:
    """Load matched rows from CSV + browser-finds that haven't been evaluated."""
    matches = []
    seen_urls: set = set()
    seen_co_title: set = set()  # cross-platform dedup: same role on LinkedIn + ATS

    if SEEN_JOBS.exists():
        with SEEN_JOBS.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("matched") == "yes" and row["job_id"] not in evaluated_ids:
                    url = row.get("url", "")
                    key = _company_title_key(row)
                    if url not in seen_urls and key not in seen_co_title:
                        seen_urls.add(url)
                        seen_co_title.add(key)
                        matches.append(row)

    if BROWSER_FINDS.exists():
        for entry in json.loads(BROWSER_FINDS.read_text(encoding="utf-8")):
            if entry.get("job_id") not in evaluated_ids:
                url = entry.get("url", "")
                key = _company_title_key(entry)
                if url not in seen_urls and key not in seen_co_title:
                    seen_urls.add(url)
                    seen_co_title.add(key)
                    matches.append(entry)

    return matches


def _kw_match(keyword: str, text: str) -> bool:
    """Match keyword against text. Short keywords (≤4 chars) use word boundaries
    to avoid false positives like 'seo' matching 'Seoul'."""
    if len(keyword) <= 4:
        return bool(re.search(r'\b' + re.escape(keyword) + r'\b', text))
    return keyword in text


def prefilter(matches: list[dict]) -> list[dict]:
    """Keep only roles that match target disciplines; apply hard exclusions."""
    cutoff = date.today() - timedelta(days=MAX_AGE_DAYS)
    keep = []
    for m in matches:
        # Drop listings older than MAX_AGE_DAYS
        found_date_str = m.get("found_date", "")
        if found_date_str:
            try:
                if date.fromisoformat(found_date_str) < cutoff:
                    continue
            except ValueError:
                pass

        title   = m.get("title", "").lower()
        company = m.get("company", "").lower()

        # Must contain at least one target keyword
        if not any(_kw_match(kw, title) for kw in REQUIRED_TITLE_KEYWORDS):
            continue
        # Hard blocklist overrides the allowlist
        if any(kw in title for kw in SKIP_TITLE_WORDS):
            continue
        if any(kw in company for kw in SKIP_INDUSTRY_WORDS):
            continue
        if any(kw in title for kw in US_AUTH_TITLE_SIGNALS):
            continue
        if any(co in company for co in US_ONLY_COMPANIES):
            continue
        if any(co in company for co in BLOCKED_COMPANIES):
            continue

        keep.append(m)
    return keep


# ---------------------------------------------------------------------------
# Extract only scoring-relevant sections from CLAUDE.md
# ---------------------------------------------------------------------------

EVAL_SECTIONS = [
    "Hard Rules for Claude",
    "Scoring Rubric",
    "Weighted Score Formula",
    "Apply Threshold",
    "My Real Skills",
    "What I Genuinely Do NOT Have",
    "Context for Evaluations",
]

def extract_eval_context(full_text: str) -> str:
    """Return only the rubric/skills sections from CLAUDE.md — skip writing rules, workflow docs."""
    lines = full_text.split("\n")
    out, capturing = [], False
    stop_headers = {"Writing Voice Rules", "Scanning Workflow", "Outreach Tracker",
                    "Applications Pipeline", "Script Split", "Running Both"}
    for line in lines:
        header = line.lstrip("#").strip()
        if any(s in header for s in EVAL_SECTIONS):
            capturing = True
        elif line.startswith("#") and any(s in header for s in stop_headers):
            capturing = False
        if capturing:
            out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Fetch posting content
# ---------------------------------------------------------------------------

# Text patterns that mean the role is closed — skip before wasting an API call.
CLOSED_SIGNALS = [
    "no longer accepting applications",
    "this job is no longer",
    "this position is no longer",
    "position has been filled",
    "this position has been filled",
    "this role has been filled",
    "this job has been filled",
    "job is closed",
    "this listing is closed",
    "this posting is closed",
    "job listing is closed",
    "application period has closed",
    "no longer available",
    "this listing has expired",
    "listing has expired",
    "job expired",
    "expired job",
    "we are not accepting",
    "not currently accepting",
    "applications are closed",
]

# fetch_posting returns:
#   None  → dead URL (4xx) or posting explicitly closed — skip entirely
#   ""    → site blocked the request (login wall, CAPTCHA) — score from title/company
#   str   → posting text


def fetch_posting(url: str):
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
        if resp.status_code in (403, 404, 410):
            return None  # dead URL — skip
        if resp.status_code != 200:
            return ""    # other error — score from title/company
        soup = BeautifulSoup(resp.content, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        text_lower = text.lower()
        if any(signal in text_lower for signal in CLOSED_SIGNALS):
            return None  # posting closed — skip
        return text[:4000]
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
        max_tokens=1000,
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
    parser.add_argument("--limit", type=int, default=0,
                        help="Cap evaluations per run (0 = no cap)")
    args = parser.parse_args()

    key_file = Path.home() / ".anthropic_key"
    if key_file.exists():
        api_key = key_file.read_text(encoding="ascii").strip()
    else:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key and not args.dry_run:
        sys.exit("API key not found.\nRun: python3 setup_key.py")

    rubric = extract_eval_context(CLAUDE_MD.read_text(encoding="utf-8")) if CLAUDE_MD.exists() else ""
    resume = MASTER_RESUME.read_text(encoding="utf-8") if MASTER_RESUME.exists() else ""

    evaluated_ids = load_evaluated_ids()
    matches       = load_new_matches(evaluated_ids)
    matches       = prefilter(matches)

    if not matches:
        print("No new matches to evaluate.")
        return

    if args.limit and args.limit > 0:
        matches = matches[:args.limit]

    total = len(matches)
    print(f"{total} candidates after pre-filtering. "
          f"{'Dry run.' if args.dry_run else 'Evaluating all.'}\n")

    if args.dry_run:
        for m in matches:
            print(f"  {m['company']}: {m['title']}")
            print(f"    {m['url']}")
        return

    client = anthropic.Anthropic(api_key=api_key)

    # Validate API key with a minimal call before processing the full batch
    print("Validating API key ... ", end="", flush=True)
    try:
        client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=5,
            messages=[{"role": "user", "content": "ping"}],
        )
        print("ok\n")
    except anthropic.AuthenticationError as e:
        sys.exit(f"ERROR: Authentication failed — {e}\n"
                 "Check billing at https://console.anthropic.com/settings/billing")
    except UnicodeEncodeError:
        sys.exit("ERROR: ANTHROPIC_API_KEY contains non-ASCII characters — the key was "
                 "likely pasted with smart quotes or invisible characters.\n"
                 "Fix: delete the export line from ~/.zshrc, paste the key fresh using "
                 "single straight quotes, then run: source ~/.zshrc")
    except Exception as e:
        sys.exit(f"ERROR: Could not reach Anthropic API — {e}\n"
                 "Check your internet connection and try again.")

    evaluated = 0

    for m in matches:
        company = m.get("company", "Unknown")
        title   = m.get("title", "Unknown")
        url     = m.get("url", "")
        job_id  = m.get("job_id", f"noid-{slugify(company)}-{slugify(title)}")

        print(f"  [{evaluated + 1}/{total}] {company} — {title}")
        print(f"    Fetching posting ... ", end="", flush=True)
        posting_text = fetch_posting(url)
        if posting_text is None:
            print("CLOSED or dead URL — skipping")
            # Write a tombstone so this job_id is never re-queued
            save_evaluation(job_id, company, title,
                            f"<!-- SKIPPED: posting closed or URL dead -->\n"
                            f"**{company} — {title}**\n"
                            f"*URL returned 403/404 or posting says no longer accepting.*\n"
                            f"**Verdict: SKIP**\n")
            continue
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
