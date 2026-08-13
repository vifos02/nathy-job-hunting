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

Output:

---
# Job Hunt Digest — [YYYY-MM-DD, HH:MM]

## Pipeline
| Company | Role | Score | Status | Next Step |
|---------|------|-------|--------|-----------|

## Top Unactioned (APPLY verdict, not yet applied)
Every row MUST include a clickable URL to the job posting.
Flag disqualified roles (US-only, 401K, short contract) inline.

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
