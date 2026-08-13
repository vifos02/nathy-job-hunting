Score the job posting below against Nathália's rubric in CLAUDE.md.

Steps:
1. Read CLAUDE.md fully before scoring anything. Pay attention to the Location Timeline and Work Authorization section.
2. Read the posting carefully, noting: role level, location/remote policy, salary (or estimate from company size), company background, required skills, **contract duration**, and any benefits that reveal employment type.
3. Before scoring, explicitly check for these signals in the full posting text — stop immediately if any are found:
   - **Closed posting**: "no longer accepting applications", "position has been filled", "this job is no longer", "applications are closed", "listing has expired" → Verdict: SKIP immediately, note the posting is closed
   - **US work authorization**: "W-2", "must be authorized to work in the US", "US citizens only", "across the country" (means US-only remote), "across the US"
   - **US employment type**: "401(k)", "401K" benefit mentioned → confirms US W-2 role, not a contractor or international hire
   - **Contract duration**: if the posting specifies a fixed contract term (e.g. "4-month contract", "6-month engagement") and Nathália is looking for a permanent or long-term role, flag this explicitly
   - If any of the above are present, set Remote/Location = 1 and Verdict = SKIP with explanation
4. Score each dimension 1–10 using the rubric.
   - Remote/Location: distinguish between work authorization requirements (hard block, score 1–2) and timezone requirements (not a block from Brazil, score 6–7 for US East Coast hours).
5. Calculate the weighted final score.
6. Give a clear APPLY / CONSIDER / SKIP verdict.
7. List the top 3 reasons to apply and the top 3 honest concerns.
8. List which resume bullets from resume/master-resume.md are most relevant to lead with.
9. Flag any hard dealbreakers from CLAUDE.md.

After the evaluation output, run the **Watchlist Check**:

### Watchlist Check

Detect the company's ATS platform from the posting URL or careers page:
- `boards.greenhouse.io/{slug}` → greenhouse, slug = {slug}
- `jobs.lever.co/{slug}` → lever, slug = {slug}
- `jobs.ashbyhq.com/{slug}` → ashby, slug = {slug}
- `apply.workable.com/{slug}` → workable, slug = {slug}
- `{slug}.breezy.hr` → breezy, slug = {slug}
- LinkedIn/Indeed/aggregator → note "no direct ATS found"

Read watchlist.json. If the company is already in watchlist.json, write: "Already in watchlist."

If **Final Score ≥ 8.5** and company NOT already in watchlist:
- Add to watchlist.json immediately (git add + commit not required yet, just write the file)
- Write: "Added to watchlist.json — score ≥ 8.5"
- If no ATS detected, write: "Watchlist entry added with platform TBD — verify ATS URL manually"

If **Final Score 7.0–8.4** and company NOT already in watchlist:
- Add to watchlist.json if ALL three conditions hold:
  1. Remote/Location score ≥ 7 (role is clearly workable from Spain/Brazil without US auth)
  2. Company Quality score ≥ 7 (established company, not a one-off staffing post)
  3. ATS platform is detectable (we can actually scan them)
- If added: "Added to watchlist.json — score in 7.0–8.4 range and all criteria met"
- If not added, state which criterion failed

If **Final Score < 7.0**: no watchlist action, write: "Score below APPLY threshold — no watchlist action"

---

Output format — follow this exactly:

---
**[Company Name] — [Role Title]**
*Source: [where you found it] | Evaluated: [today's date]*

| Dimension | Score | Reasoning |
|-----------|-------|-----------|
| Role Fit (30%) | /10 | |
| Remote / Location (25%) | /10 | |
| Compensation (20%) | /10 | |
| Company Quality (15%) | /10 | |
| Skill Match (10%) | /10 | |
| **Final Score** | **/10** | |

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
- [ ] US work authorization required (W-2, visa sponsorship, citizenship)
- [ ] US-only remote ("across the country", "across the US", or US states listed as location)
- [ ] 401(k) / 401K benefit listed (confirms US W-2 employment)
- [ ] Posting closed / no longer accepting applications
- [ ] Short-term contract (specify duration if yes)
- [ ] On-site in city I won't be in
- [ ] BRL-only pay below R$15k
- Others:

**Save this evaluation to:** `evaluations/[YYYY-MM-DD]-[company]-[role-slug].md`

---

**Watchlist Check**
[ATS platform detected / not detected]
[Watchlist action taken or reason not taken]

---

POSTING:
$ARGUMENTS
