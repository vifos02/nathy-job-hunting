"""
Rebuilds index.html from all digests/*.html files.
Run after each new digest is generated:
    python3 update_index.py
"""

import os
import re

DIGESTS_DIR = os.path.join(os.path.dirname(__file__), "digests")
INDEX_PATH = os.path.join(os.path.dirname(__file__), "index.html")


def list_digests():
    files = []
    for name in os.listdir(DIGESTS_DIR):
        if re.match(r"\d{4}-\d{2}-\d{2}-\d{4}\.html$", name):
            files.append(name)
    return sorted(files, reverse=True)


def label(filename):
    stem = filename.replace(".html", "")
    # stem = YYYY-MM-DD-HHMM
    parts = stem.split("-")
    if len(parts) == 4:
        date = f"{parts[0]}-{parts[1]}-{parts[2]}"
        time = f"{parts[3][:2]}:{parts[3][2:]}"
        return f"{date} {time}"
    return stem


def build_index(files):
    rows = []
    for i, f in enumerate(files):
        lbl = label(f)
        badge = '<span class="badge latest">latest</span>' if i == 0 else ""
        cls = " class=\"latest\"" if i == 0 else ""
        rows.append(f'  <li{cls}><a href="digests/{f}">{lbl} {badge}</a></li>')
    rows_html = "\n".join(rows)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Nathy Job Hunt</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:system-ui,sans-serif;background:#f9f9f7;color:#1a1a1a;padding:2rem 1rem;max-width:640px;margin:0 auto;font-size:15px}}
h1{{font-size:1.15rem;font-weight:700;margin-bottom:.25rem}}
.sub{{color:#666;font-size:.82rem;margin-bottom:2rem}}
.digest-list{{list-style:none}}
.digest-list li{{border-bottom:1px solid #ebebeb}}
.digest-list li:first-child{{border-top:1px solid #ebebeb}}
.digest-list a{{display:flex;justify-content:space-between;align-items:center;padding:.7rem 0;color:#1d4ed8;text-decoration:none;font-size:.92rem}}
.digest-list a:hover{{color:#1e3a8a}}
.badge{{font-size:.72rem;background:#f0f0f0;color:#555;padding:.15rem .5rem;border-radius:99px;white-space:nowrap;margin-left:.75rem}}
.latest .badge{{background:#dcfce7;color:#15803d}}
</style>
</head>
<body>
<h1>Nathy Job Hunt — Digests</h1>
<p class="sub">Updated after each scan cycle. Open the latest to see new matches and action items.</p>
<ul class="digest-list">
{rows_html}
</ul>
</body>
</html>
"""


def main():
    files = list_digests()
    if not files:
        print("No digest HTML files found in digests/")
        return
    html = build_index(files)
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"index.html updated — {len(files)} digest(s) listed")


if __name__ == "__main__":
    main()
