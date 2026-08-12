#!/bin/bash
# Daily job scan — runs twice a day via cron.
# Pulls latest, runs both scanners, commits and pushes results.
# Run from any branch — push goes to the current branch.

REPO_DIR="$HOME/nathy-job-hunting"
LOGFILE="$REPO_DIR/scan.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M')

echo "" >> "$LOGFILE"
echo "=== $TIMESTAMP ===" >> "$LOGFILE"

cd "$REPO_DIR" || exit 1

git pull >> "$LOGFILE" 2>&1

python3 scan_jobs.py >> "$LOGFILE" 2>&1 || echo "scan_jobs.py exited with error" >> "$LOGFILE"
python3 browser_search.py >> "$LOGFILE" 2>&1 || echo "browser_search.py exited with error" >> "$LOGFILE"
python3 evaluate_matches.py >> "$LOGFILE" 2>&1 || echo "evaluate_matches.py exited with error" >> "$LOGFILE"

git add evaluated-jobs.csv >> "$LOGFILE" 2>&1
git add browser-finds.json >> "$LOGFILE" 2>&1 || true
git add evaluations/ >> "$LOGFILE" 2>&1 || true

git diff --cached --quiet && echo "Nothing new to commit." >> "$LOGFILE" || \
  git commit -m "scan $(date +%Y-%m-%d-%H%M)" >> "$LOGFILE" 2>&1

git push >> "$LOGFILE" 2>&1

echo "Done." >> "$LOGFILE"
