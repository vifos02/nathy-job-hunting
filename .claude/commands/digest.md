Generate a job hunt digest — a snapshot of the current pipeline and new unscored matches.

Run this any time after a scan or evaluation cycle. Both scanners run locally on your Mac (twice a day — morning and mid-afternoon) and push results to the repo. Open a Claude Web session and run /digest to review what they found.

Steps:
1. Read CLAUDE.md for workflow context and scoring rubric.
2. Read applications.csv and group by status.

3. **Delta detection — do this before reading evaluations:**
   - List all files in digests/ sorted by filename (which is chronological).
   - The most recent **markdown** file (*.md) is the previous digest. Read it and extract:
     a. Every company+role row from its "Evaluated This Period" table → call this PREV_EVALUATED.
     b. Every company+role row from its "New Unscored Matches" sections → call this PREV_UNSCORED.
   - If no previous digest exists, PREV_EVALUATED and PREV_UNSCORED are empty (full digest mode).

4. Read all files in evaluations/ and extract scores, verdicts, and source URLs. The URL is on the *Source:* line near the top of each file.
   - **NEW evaluations** = evaluation files whose company+role combination is NOT in PREV_EVALUATED.
   - **PREVIOUSLY REPORTED** = evaluation files whose company+role IS in PREV_EVALUATED (suppress from "Evaluated Since Last Digest" — do not re-list them).

5. Read evaluated-jobs.csv — find rows where matched=yes that have no corresponding file in evaluations/.
6. Read browser-finds.json — find entries where matched=yes that have no corresponding file in evaluations/.

   **Deduplicate steps 5+6 by job_id before counting.** Both scanners write to evaluated-jobs.csv as the shared dedup record, so LinkedIn jobs appear in both files. The only true unique count is the union by job_id.
   - **NEW unscored (unique)** = job_ids in the union of steps 5+6 that are NOT in PREV_UNSCORED.
   - When listing unscored matches in the output sections, split by source (API vs browser) for readability, but never show separate totals — only the single deduplicated count matters.

7. Check companies.md for Tier 1 companies with no recent evaluation — flag as "not yet checked."

8. Save the digest text to digests/YYYY-MM-DD-HHMM.md (use the actual timestamp).

9. **Write a simple HTML version** to digests/YYYY-MM-DD-HHMM.html (same timestamp as the .md).
   Use the template below — fill in the data, keep the HTML minimal. No external resources, no dark-mode complexity, no fonts. The goal is fast generation and small file size.

   ```html
   <!DOCTYPE html>
   <html lang="en">
   <head>
   <meta charset="utf-8">
   <title>Digest YYYY-MM-DD HH:MM</title>
   <style>
   body{font-family:system-ui,sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem;color:#1a1a1a;font-size:15px}
   h1{font-size:1.3rem;margin-bottom:.25rem}
   .sub{color:#666;font-size:.85rem;margin-bottom:1.5rem}
   h2{font-size:1rem;border-bottom:1px solid #e0e0e0;padding-bottom:.3rem;margin-top:2rem}
   table{border-collapse:collapse;width:100%;font-size:.88rem}
   th{text-align:left;padding:.35rem .6rem;background:#f2f2f2;white-space:nowrap}
   td{padding:.35rem .6rem;border-bottom:1px solid #efefef;vertical-align:top}
   tr.apply td:first-child{border-left:3px solid #16a34a}
   tr.consider td:first-child{border-left:3px solid #d97706}
   tr.unscored td:first-child{border-left:3px solid #9ca3af}
   .pill{display:inline-block;padding:.05rem .45rem;border-radius:99px;font-size:.75rem;font-weight:600}
   .p-apply{background:#dcfce7;color:#15803d}
   .p-consider{background:#fef3c7;color:#92400e}
   .p-skip{background:#fee2e2;color:#b91c1c}
   .stats{display:flex;flex-wrap:wrap;gap:1.5rem;background:#f8f8f8;padding:.9rem 1rem;border-radius:6px;margin:1rem 0 1.5rem}
   .stat .n{font-size:1.6rem;font-weight:700;line-height:1}
   .stat .l{font-size:.75rem;color:#666;margin-top:.1rem}
   a{color:#1d4ed8}
   ul{margin:.4rem 0;padding-left:1.3rem}
   li{margin:.2rem 0}
   p{margin:.5rem 0}
   </style>
   </head>
   <body>
   <h1>Job Hunt Digest — YYYY-MM-DD HH:MM</h1>
   <p class="sub">Delta since PREV_DIGEST_FILENAME (or "Full digest")</p>

   <div class="stats">
     <div class="stat"><div class="n">X</div><div class="l">Evaluated all-time</div></div>
     <div class="stat"><div class="n">X</div><div class="l">APPLY</div></div>
     <div class="stat"><div class="n">X</div><div class="l">CONSIDER</div></div>
     <div class="stat"><div class="n">X</div><div class="l">Unscored (new)</div></div>
     <div class="stat"><div class="n">X</div><div class="l">Applied</div></div>
   </div>

   <h2>New APPLY Since Last Digest</h2>
   <table>
   <tr><th>Role</th><th>Company</th><th>Score</th><th>Status</th></tr>
   <!-- one <tr class="apply"> per row; role cell = <td><a href="URL" target="_blank">Title</a></td> -->
   </table>

   <h2>New CONSIDER Since Last Digest</h2>
   <table>
   <tr><th>Role</th><th>Company</th><th>Score</th><th>Status</th></tr>
   </table>

   <h2>New Unscored — API Sources</h2>
   <table>
   <tr><th>Role</th><th>Company</th><th>Found</th></tr>
   </table>

   <h2>New Unscored — Browser Sources</h2>
   <table>
   <tr><th>Role</th><th>Company</th><th>Found</th></tr>
   </table>

   <h2>Tier 1 Not Yet Checked</h2>
   <ul><!-- <li>Company name</li> --></ul>

   <h2>Action Items</h2>
   <ol><!-- <li>...</li> --></ol>

   <h2>Outreach</h2>
   <table>
   <tr><th>Person</th><th>Company</th><th>Platform</th><th>Status</th><th>Follow-up Due</th></tr>
   </table>

   <h2>Stats</h2>
   <ul>
   <li>API scan seen: X total | X matched</li>
   <li>Browser scan seen: X total</li>
   <li>Unscored unique: X total | X new since last digest</li>
   <li>Evaluated all-time: X (X new since last digest)</li>
   <li>Pipeline: Applied X | Screening X | Interview X | Offers X</li>
   <li>Outreach: X sent | X replied (X%) | X meetings booked</li>
   </ul>

   </body>
   </html>
   ```

   Rules for the HTML:
   - Every job row must be a clickable link. No URL from the evaluation file → omit the row.
   - Do NOT include SKIP / disqualified roles. Omit them entirely.
   - Sort scored sections by final score descending.
   - Rows use class `apply`, `consider`, or `unscored` on the `<tr>` for the left-border stripe.
   - Verdict pill uses class `p-apply`, `p-consider`, or `p-skip`.

10. Commit and push both files in one go:
    ```
    git add digests/YYYY-MM-DD-HHMM.md digests/YYYY-MM-DD-HHMM.html
    git commit -m "digest YYYY-MM-DD-HHMM"
    git push
    ```
    Confirm the push succeeded.
    Then tell the user: **`open digests/YYYY-MM-DD-HHMM.html`** to view it in their browser.

    Do NOT use the Artifact tool. The HTML file is the deliverable.

---

Output:

---
# Job Hunt Digest — [YYYY-MM-DD, HH:MM]
*(Delta since [previous digest filename], or "Full digest — no previous digest found")*

## Pipeline
| Company | Role | Score | Status | Next Step |
|---------|------|-------|--------|-----------|

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
- API scan seen: X total | X matched
- Browser scan seen: X total (all matched=yes)
- Unscored unique: X total | X new since last digest (deduplicated across both sources by job_id)
- Evaluated all-time: X (X new since last digest)
- Pipeline: Applied X | Screening X | Interview X | Offers X
- Outreach: X sent | X replied (X% reply rate) | X meetings booked
---
