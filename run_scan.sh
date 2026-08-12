#!/bin/bash
# Daily job scan — runs twice a day via cron.
# Pulls latest, runs both scanners, commits and pushes results.

set -e

REPO_DIR="$HOME/nathy-job-hunting"
LOGFILE="$REPO_DIR/scan.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M')

echo "" >> "$LOGFILE"
echo "=== $TIMESTAMP ===" >> "$LOGFILE"

cd "$REPO_DIR"

git pull origin main >> "$LOGFILE" 2>&1

python3 scan_jobs.py >> "$LOGFILE" 2>&1
python3 browser_search.py >> "$LOGFILE" 2>&1

git add evaluated-jobs.csv >> "$LOGFILE" 2>&1
git add browser-finds.json >> "$LOGFILE" 2>&1 || true

git diff --cached --quiet && echo "Nothing new to commit." >> "$LOGFILE" || \
  git commit -m "scan $(date +%Y-%m-%d-%H%M)" >> "$LOGFILE" 2>&1

git push origin main >> "$LOGFILE" 2>&1

echo "Done." >> "$LOGFILE"
