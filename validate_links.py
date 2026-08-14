"""
Link validator for APPLY and CONSIDER evaluation files.

Reads all evaluations/ files with verdict APPLY or CONSIDER, extracts their
source URLs, and makes a HEAD request to each one. Results are written to
link-status.json as {url: status_code}.

The /digest command reads link-status.json to flag broken links with ⚠️.

Run this locally before running /digest (takes 2-5 minutes for ~100 URLs):
    python3 validate_links.py

Options:
    --apply-only     Only check APPLY files (faster, for quick scans)
    --verbose        Print each URL and its status
"""

import argparse
import json
import re
import time
from pathlib import Path

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    import sys
    sys.exit("requests not installed. Run: pip install requests")

ROOT = Path(__file__).parent
EVALS_DIR = ROOT / "evaluations"
OUTPUT_PATH = ROOT / "link-status.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}

BROKEN = {404, 410}
FLAG = {403, 404, 410}  # flag these in the digest


def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=2, backoff_factor=1, status_forcelist=[429, 503])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


def extract_url_and_verdict(path: Path) -> tuple[str | None, str | None]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    url = None
    verdict = None
    for line in text.splitlines():
        if url is None and line.startswith("*Source:"):
            m = re.search(r"https?://\S+", line)
            if m:
                url = m.group(0).rstrip("*").rstrip()
        if verdict is None:
            m = re.search(r"\*\*Verdict:\s*(APPLY|CONSIDER|SKIP)\*\*", line, re.I)
            if m:
                verdict = m.group(1).upper()
        if url and verdict:
            break
    return url, verdict


def collect_urls(apply_only: bool) -> list[str]:
    targets = {"APPLY"} if apply_only else {"APPLY", "CONSIDER"}
    urls = []
    seen = set()
    for f in sorted(EVALS_DIR.glob("*.md")):
        url, verdict = extract_url_and_verdict(f)
        if url and verdict in targets and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def check_url(session: requests.Session, url: str, verbose: bool) -> int:
    try:
        resp = session.head(url, headers=HEADERS, timeout=12, allow_redirects=True)
        status = resp.status_code
        # Some servers don't support HEAD — retry with GET (no body)
        if status in (405, 501):
            resp = session.get(
                url, headers=HEADERS, timeout=12, allow_redirects=True, stream=True
            )
            resp.close()
            status = resp.status_code
    except Exception:
        status = 0  # network error / timeout — don't flag as broken
    if verbose:
        marker = " ⚠️" if status in FLAG else ""
        print(f"  {status}{marker}  {url}")
    return status


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply-only", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    urls = collect_urls(args.apply_only)
    if not urls:
        print("No APPLY/CONSIDER evaluation files found.")
        return

    tier = "APPLY" if args.apply_only else "APPLY + CONSIDER"
    print(f"Checking {len(urls)} {tier} URLs...")

    session = _build_session()
    results: dict[str, int] = {}
    flagged = 0

    for i, url in enumerate(urls, 1):
        status = check_url(session, url, args.verbose)
        results[url] = status
        if status in FLAG:
            flagged += 1
        if i % 10 == 0:
            print(f"  {i}/{len(urls)} done...")
        time.sleep(0.3)

    OUTPUT_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nDone. {flagged} broken/restricted links flagged. Results → link-status.json")
    if flagged:
        broken_urls = [u for u, s in results.items() if s in FLAG]
        for u in broken_urls:
            print(f"  ⚠️  {results[u]}  {u}")


if __name__ == "__main__":
    main()
