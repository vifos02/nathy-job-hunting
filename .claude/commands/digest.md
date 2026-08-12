Generate a job hunt digest — a snapshot of the current pipeline and new unscored matches.

Run this any time after a scan cycle. The system runs scans twice a day (morning and mid-afternoon), so the digest reflects whichever run just completed or the full day's picture.

Steps:
1. Read CLAUDE.md for workflow context and scoring rubric.
2. Read applications.csv and group by status.
3. Read all files in evaluations/ and extract scores and verdicts.
4. Read evaluated-jobs.csv — find rows where matched=yes that have no corresponding file in evaluations/. These are unscored API matches awaiting review.
5. Read browser-finds.json — these are unscored browser matches (Indeed, LinkedIn, Remote.co) awaiting review.
6. Check companies.md for Tier 1 companies with no recent evaluation — flag as "not yet checked."

Output:

---
# Job Hunt Digest — [YYYY-MM-DD, HH:MM]

## Pipeline
| Company | Role | Score | Status | Next Step |
|---------|------|-------|--------|-----------|

## Top Unactioned (APPLY verdict, not yet applied)

## New Unscored Matches — API Sources
List company, title, URL for each evaluated-jobs.csv row where matched=yes and no evaluations/ file exists.
If none: "None — all API matches have been evaluated."

## New Unscored Matches — Browser Sources
List company, title, URL, source for each entry in browser-finds.json.
If file is empty or missing: "No browser scan results yet. Run browser_search.py locally."

## Evaluated This Period
| Company | Role | Score | Verdict | Date |
|---------|------|-------|---------|------|

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
