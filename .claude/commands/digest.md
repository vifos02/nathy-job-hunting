Generate a job hunt digest — a snapshot of the current pipeline and new unscored matches.

Run this any time after a scan cycle. Both scanners run locally on your Mac (twice a day — morning and mid-afternoon) and push results to the repo. Open a Claude Web session and run /digest to review what they found.

Steps:
1. Read CLAUDE.md for workflow context and scoring rubric.
2. Read applications.csv and group by status.
3. Read all files in evaluations/ and extract scores, verdicts, and source URLs. The URL is on the *Source:* line near the top of each file.
4. Read evaluated-jobs.csv — find rows where matched=yes that have no corresponding file in evaluations/. These are unscored API matches awaiting review.
5. Read browser-finds.json — these are unscored browser matches (Indeed, LinkedIn, Remote.co) awaiting review.
6. Check companies.md for Tier 1 companies with no recent evaluation — flag as "not yet checked."
7. After generating the digest, save it to digests/YYYY-MM-DD-HHMM.md (use the actual timestamp), then run:
   git add digests/YYYY-MM-DD-HHMM.md && git commit -m "digest YYYY-MM-DD-HHMM" && git push
   Confirm the push succeeded at the end of your output.

8. **Always publish an interactive HTML artifact** after the git push. Build the digest as a self-contained HTML page and publish it using the Artifact tool so it appears inline and can be opened in a browser tab. Requirements for the HTML:
   - Stat bar at the top: total evaluated, active APPLY count, CONSIDER count, unevaluated API count, browser finds count, applied count.
   - Sections: APPLY Candidates, CONSIDER, Unscored Highlights, Tier 1 Not Checked, Action Items, Stats.
   - Every job row must be a clickable link (`<a href="..." target="_blank">`). No URL, no row.
   - Rows are color-coded by status using a left-border stripe: green = APPLY, amber = CONSIDER, blue = verify first, red = disqualified, grey = unscored.
   - Each row shows: role title (linked), company, score (monospace), verdict pill.
   - Do NOT include disqualified roles (US-only, 401K, short contract, or any confirmed hard dealbreaker). Omit them entirely — they are not actionable.
   - Flag staffing-agency rows that need verification before applying (blue stripe, "Verify first" pill).
   - Designs both light and dark themes via CSS custom properties.
   - Use the Artifact tool with favicon "📋" and a description of the form "Job hunt snapshot — YYYY-MM-DD".
   - Redeploy to the same artifact URL if one was already published this session (pass the existing URL). Otherwise publish fresh.

Output:

---
# Job Hunt Digest — [YYYY-MM-DD, HH:MM]

## Pipeline
| Company | Role | Score | Status | Next Step |
|---------|------|-------|--------|-----------|

## Top Unactioned (APPLY verdict, not yet applied)
Every row MUST include a clickable URL to the job posting.
**Do NOT list disqualified roles** (US-only, 401K, short-term contract, or any other hard dealbreaker confirmed by manual review). They are off the list — omit them entirely. Only show roles that are actionable.
**Do NOT list closed or dead postings** — any role whose evaluation file contains "SKIPPED: posting closed or URL dead", or whose verdict is SKIP due to a 403/404 URL. These are gone and should not reappear.

## New Unscored Matches — API Sources
Every row MUST include the URL from evaluated-jobs.csv.
List company, title, URL for each evaluated-jobs.csv row where matched=yes and no evaluations/ file exists.
If none: "None — all API matches have been evaluated."

## New Unscored Matches — Browser Sources
Every row MUST include the URL from browser-finds.json.
List company, title, URL, source for each entry in browser-finds.json.
If file is empty or missing: "No browser scan results yet. Run browser_search.py locally."

## Evaluated This Period
Every row MUST include the URL extracted from the evaluation file's Source line.
| Company | Role | Score | Verdict | URL | Date |
|---------|------|-------|---------|-----|------|

## Tier 1 Companies Not Yet Checked

## Action Items
1.
2.
3.

## Outreach
Read outreach-tracker.csv and show:
- Contacts due for follow-up (follow_up_date ≤ today, status = Sent or No Response)
- Reply rate so far: Replied or Meeting Booked / total Sent

| Person | Company | Platform | Status | Follow-up Due |
|--------|---------|----------|--------|---------------|

## Stats
- API scan seen: X total | X matched | X evaluated
- Browser scan seen: X total | X in browser-finds.json
- Pipeline: Applied X | Screening X | Interview X | Offers X
- Outreach: X sent | X replied (X% reply rate) | X meetings booked
---
