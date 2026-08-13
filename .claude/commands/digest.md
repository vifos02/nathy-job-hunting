Generate a job hunt digest — a snapshot of the current pipeline and new unscored matches.

Run this any time after a scan or evaluation cycle. Both scanners run locally on your Mac (twice a day — morning and mid-afternoon) and push results to the repo. Open a Claude Web session and run /digest to review what they found.

Steps:
1. Read CLAUDE.md for workflow context and scoring rubric.
2. Read applications.csv and group by status.

3. **Delta detection — do this before reading evaluations:**
   - List all files in digests/ sorted by filename (which is chronological).
   - The most recent file is the previous digest. Read it and extract:
     a. Every company+role row from its "Evaluated This Period" table → call this PREV_EVALUATED.
     b. Every company+role row from its "New Unscored Matches" sections → call this PREV_UNSCORED.
   - If no previous digest exists, PREV_EVALUATED and PREV_UNSCORED are empty (full digest mode).

4. Read all files in evaluations/ and extract scores, verdicts, and source URLs. The URL is on the *Source:* line near the top of each file.
   - **NEW evaluations** = evaluation files whose company+role combination is NOT in PREV_EVALUATED.
   - **PREVIOUSLY REPORTED** = evaluation files whose company+role IS in PREV_EVALUATED (suppress from "Evaluated Since Last Digest" — do not re-list them).

5. Read evaluated-jobs.csv — find rows where matched=yes that have no corresponding file in evaluations/. These are unscored API matches awaiting review.
   - **NEW unscored API** = rows not mentioned in PREV_UNSCORED.

6. Read browser-finds.json — these are unscored browser matches (LinkedIn, Glassdoor, Indeed, Remote.co, InfoJobs) awaiting review.
   - **NEW browser finds** = entries not mentioned in PREV_UNSCORED.

7. Check companies.md for Tier 1 companies with no recent evaluation — flag as "not yet checked."

8. After generating the digest, save it to digests/YYYY-MM-DD-HHMM.md (use the actual timestamp), then run:
   git add digests/YYYY-MM-DD-HHMM.md && git commit -m "digest YYYY-MM-DD-HHMM" && git push
   Confirm the push succeeded at the end of your output.

9. **Always publish an interactive HTML artifact** after the git push. Build the digest as a self-contained HTML page and publish it using the Artifact tool so it appears inline and can be opened in a browser tab. Requirements for the HTML:
   - Stat bar at the top: total evaluated (all time), active APPLY count (all time), CONSIDER count (all time), unevaluated API count (new only), browser finds count (new only), applied count.
   - Sections: New APPLY Candidates, New CONSIDER, Unscored Highlights (new only), Tier 1 Not Checked, Action Items, Stats.
   - Within each scored section, rows are sorted by final score descending (highest score at the top).
   - Every job row must be a clickable link (`<a href="..." target="_blank">`). No URL, no row.
   - Rows are color-coded by status using a left-border stripe: green = APPLY, amber = CONSIDER, blue = verify first, red = disqualified, grey = unscored.
   - Each row shows: role title (linked), company, score (monospace), verdict pill.
   - Do NOT include disqualified roles (US-only, 401K, short contract, or any confirmed hard dealbreaker). Omit them entirely — they are not actionable.
   - Flag staffing-agency rows that need verification before applying (blue stripe, "Verify first" pill).
   - Designs both light and dark themes via CSS custom properties.
   - Use the Artifact tool with favicon "📋" and a description of the form "Job hunt snapshot — YYYY-MM-DD".
   - Redeploy to the same artifact URL if one was already published this session (pass the existing URL). Otherwise publish fresh.

---

Output:

---
# Job Hunt Digest — [YYYY-MM-DD, HH:MM]
*(Delta since [previous digest filename], or "Full digest — no previous digest found")*

## Pipeline
| Company | Role | Score | Status | Next Step |
|---------|------|-------|--------|-----------|

## Top Unactioned (APPLY verdict, not yet applied)
**ALL actionable APPLY roles, not just new ones** — this is always cumulative so nothing falls off the radar.
Every row MUST include a clickable URL to the job posting.
**Sort by final score, highest to lowest.**
**Do NOT list disqualified roles** (US-only, 401K, short-term contract, or any confirmed hard dealbreaker). Omit them entirely.
**Do NOT list closed or dead postings** — any role whose evaluation file contains "SKIPPED: posting closed or URL dead". These are gone.

## New APPLY / CONSIDER Since Last Digest
Only evaluations whose company+role was NOT in the previous digest's "Evaluated This Period" table.
Every row MUST include the URL from the evaluation file's Source line.
Sort by final score, highest to lowest. Split into APPLY (≥7.0) and CONSIDER (5.5–6.9) sub-sections.
If none: "No new scored matches since last digest."

## New Unscored Matches — API Sources
Only rows not previously listed in any prior digest.
Every row MUST include the URL from evaluated-jobs.csv.
List company, title, URL for each new matched row with no evaluations/ file.
If none: "None — all API matches have been evaluated or previously reported."

## New Unscored Matches — Browser Sources
Only entries not previously listed in any prior digest.
Every row MUST include the URL from browser-finds.json.
List company, title, URL, source for each new entry in browser-finds.json.
If file is empty or missing: "No browser scan results yet. Run browser_search.py locally."

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
- API scan seen: X total | X matched | X evaluated (X new since last digest)
- Browser scan seen: X total | X in browser-finds.json (X new since last digest)
- Pipeline: Applied X | Screening X | Interview X | Offers X
- Outreach: X sent | X replied (X% reply rate) | X meetings booked
---
