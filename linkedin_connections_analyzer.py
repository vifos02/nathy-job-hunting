#!/usr/bin/env python3
"""
LinkedIn connections analyzer.

Reads LinkedIn's Connections.csv export, clusters contacts by company,
cross-references against watchlist.json and companies.md, and outputs:

  1. connections_analysis.md  — prioritized outreach list with context
  2. outreach_candidates.csv  — ready to paste into outreach-tracker.csv

Usage:
  Place LinkedIn's Connections.csv in this directory, then:
  python3 linkedin_connections_analyzer.py [--csv path/to/Connections.csv]

LinkedIn export: Settings & Privacy → Data Privacy → Get a copy of your data
→ tick "Connections" → Request archive. CSV arrives in ~10 minutes via email.
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
WATCHLIST_PATH = os.path.join(REPO_ROOT, "watchlist.json")
OUTREACH_PATH = os.path.join(REPO_ROOT, "outreach-tracker.csv")


# ---------------------------------------------------------------------------
# Companies known to have roles relevant to Nathália — mined from companies.md
# Used to flag connections at high-priority employers even if not in watchlist.
# ---------------------------------------------------------------------------
TIER1_COMPANIES = {
    # Spain-based
    "typeform", "factorial hr", "factorial", "personio", "glovo", "domestika",
    "wallapop", "semrush", "se ranking",
    # Global remote-first
    "buffer", "gitlab", "hotmart", "rock content", "monday.com", "miro",
    "notion", "hubspot", "canonical", "automattic", "doist",
    # SEO/content tool companies
    "ahrefs", "yoast", "conductor",
    # Brazilian tech
    "rd station", "rdstation", "pipefy", "gympass", "wellhub", "nuvemshop",
    "nubank", "magazine luiza", "magalu", "serasa experian",
    # Agencies
    "dept agency", "dept", "akqa", "we are social", "jellyfish", "publicis",
    "dentsu", "mirum", "jwt", "wunderman thompson",
    # Fortune 500 with SP/BCN presence
    "google", "meta", "microsoft", "amazon", "salesforce", "oracle", "sap",
    "ibm", "cisco", "netflix", "mastercard", "visa", "paypal", "uber",
    "nike", "booking", "booking.com", "accenture",
    # Other high-signal
    "canva", "deel", "remote", "stripe", "atlassian", "shopify", "squarespace",
    "mailchimp", "intercom", "zendesk", "twilio", "cloudflare",
}

# Roles that suggest the contact is a recruiter or talent professional
RECRUITER_ROLE_KEYWORDS = {
    "recruiter", "talent acquisition", "talent partner", "hr manager",
    "people partner", "people ops", "hiring manager", "head of talent",
    "recruiting", "headhunter", "staffing", "executive search",
}

# Roles that overlap with Nathália's function — these contacts may know open roles
# or be peers who can refer
PEER_ROLE_KEYWORDS = {
    "marketing", "seo", "content", "growth", "brand", "communications",
    "demand gen", "social media", "digital", "creative director",
    "marketing manager", "head of marketing", "vp marketing", "cmo",
    "gerente de marketing", "head de marketing",
}


def load_watchlist_companies():
    try:
        with open(WATCHLIST_PATH) as f:
            data = json.load(f)
        return {entry["company"].lower() for entry in data}
    except Exception:
        return set()


def detect_relationship_type(position: str) -> str:
    pos_lower = position.lower()
    if any(kw in pos_lower for kw in RECRUITER_ROLE_KEYWORDS):
        return "recruiter"
    if any(kw in pos_lower for kw in PEER_ROLE_KEYWORDS):
        return "peer"
    return "other"


def company_is_high_priority(company: str, watchlist: set) -> bool:
    c = company.lower().strip()
    if c in watchlist:
        return True
    for t1 in TIER1_COMPANIES:
        if t1 in c or c in t1:
            return True
    return False


def outreach_priority_score(contacts: list, company: str, watchlist: set) -> int:
    """
    Higher = more urgent to reach out.
    0-100 scale:
      +40  if company is Tier 1 or in watchlist
      +20  per recruiter contact at that company (max 20)
      +15  per peer contact at that company (max 30)
      +5   per additional contact (network density signal)
    """
    score = 0
    if company_is_high_priority(company, watchlist):
        score += 40
    recruiter_count = sum(1 for c in contacts if c["type"] == "recruiter")
    peer_count = sum(1 for c in contacts if c["type"] == "peer")
    score += min(recruiter_count * 20, 20)
    score += min(peer_count * 15, 30)
    score += min((len(contacts) - 1) * 5, 20)
    return score


def parse_connections_csv(path: str) -> list:
    """
    LinkedIn exports vary slightly. Handles:
    - "First Name","Last Name","URL","Email Address","Company","Position","Connected On"
    - "First Name","Last Name","Email Address","Company","Position","Connected On"

    Skips the LinkedIn boilerplate header lines (notes before the actual CSV header).
    """
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        lines = f.readlines()

    # Find the actual CSV header row (contains "First Name")
    start = 0
    for i, line in enumerate(lines):
        if "First Name" in line:
            start = i
            break

    reader = csv.DictReader(lines[start:])
    for row in reader:
        # Normalize key names (LinkedIn has changed column names across exports)
        first = (row.get("First Name") or row.get("FirstName") or "").strip()
        last = (row.get("Last Name") or row.get("LastName") or "").strip()
        company = (row.get("Company") or "").strip()
        position = (row.get("Position") or "").strip()
        email = (row.get("Email Address") or row.get("EmailAddress") or "").strip()
        connected = (row.get("Connected On") or "").strip()

        if not first and not last:
            continue
        if not company:
            company = "(no company listed)"

        rows.append({
            "name": f"{first} {last}".strip(),
            "company": company,
            "position": position,
            "email": email,
            "connected": connected,
            "type": detect_relationship_type(position),
        })
    return rows


def cluster_by_company(connections: list) -> dict:
    clusters = defaultdict(list)
    for conn in connections:
        clusters[conn["company"]].append(conn)
    return dict(clusters)


def build_outreach_priority_list(clusters: dict, watchlist: set) -> list:
    results = []
    for company, contacts in clusters.items():
        score = outreach_priority_score(contacts, company, watchlist)
        in_watchlist = company.lower() in watchlist
        is_tier1 = company_is_high_priority(company, watchlist)
        recruiters = [c for c in contacts if c["type"] == "recruiter"]
        peers = [c for c in contacts if c["type"] == "peer"]
        others = [c for c in contacts if c["type"] == "other"]
        results.append({
            "company": company,
            "score": score,
            "in_watchlist": in_watchlist,
            "is_tier1": is_tier1,
            "contacts": contacts,
            "recruiters": recruiters,
            "peers": peers,
            "others": others,
            "total": len(contacts),
        })
    results.sort(key=lambda x: (-x["score"], x["company"]))
    return results


def write_analysis(priority_list: list, total_connections: int, watchlist: set):
    today = date.today().isoformat()
    output_path = os.path.join(REPO_ROOT, "connections_analysis.md")

    in_watchlist_count = sum(1 for e in priority_list if e["in_watchlist"])
    tier1_count = sum(1 for e in priority_list if e["is_tier1"] and not e["in_watchlist"])
    recruiter_companies = sum(1 for e in priority_list if e["recruiters"])
    high_priority = [e for e in priority_list if e["score"] >= 40]

    with open(output_path, "w") as f:
        f.write(f"# LinkedIn Connections Analysis — {today}\n\n")
        f.write(f"**{total_connections} connections** across **{len(priority_list)} companies**.\n\n")
        f.write(f"- {in_watchlist_count} companies already in watchlist.json\n")
        f.write(f"- {tier1_count} additional Tier 1 targets not yet in watchlist\n")
        f.write(f"- {recruiter_companies} companies have recruiter contacts\n")
        f.write(f"- {len(high_priority)} high-priority outreach targets (score ≥ 40)\n\n")
        f.write("---\n\n")

        f.write("## High-Priority Outreach Targets\n\n")
        f.write("*Score ≥ 40: combination of Tier 1/watchlist company + recruiter or peer contacts.*\n\n")

        for entry in high_priority:
            flags = []
            if entry["in_watchlist"]:
                flags.append("in watchlist")
            elif entry["is_tier1"]:
                flags.append("Tier 1 target")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            f.write(f"### {entry['company']}{flag_str}  (score {entry['score']})\n\n")

            if entry["recruiters"]:
                f.write("**Recruiter contacts:**\n")
                for c in entry["recruiters"]:
                    email_str = f" — {c['email']}" if c["email"] else ""
                    f.write(f"- {c['name']} — {c['position']}{email_str}\n")
                f.write("\n")

            if entry["peers"]:
                f.write("**Peer contacts (marketing/SEO/content/growth):**\n")
                for c in entry["peers"]:
                    email_str = f" — {c['email']}" if c["email"] else ""
                    f.write(f"- {c['name']} — {c['position']}{email_str}\n")
                f.write("\n")

            if entry["others"]:
                f.write("**Other contacts:**\n")
                for c in entry["others"]:
                    f.write(f"- {c['name']} — {c['position']}\n")
                f.write("\n")

        f.write("---\n\n")
        f.write("## Companies to Evaluate for Watchlist Addition\n\n")
        f.write("*Tier 1 targets you have connections at, not yet in watchlist.json.*\n\n")
        f.write("| Company | Connections | Types | Action |\n")
        f.write("|---------|-------------|-------|--------|\n")
        new_for_watchlist = [e for e in priority_list if e["is_tier1"] and not e["in_watchlist"]]
        for entry in new_for_watchlist:
            types = []
            if entry["recruiters"]:
                types.append(f"{len(entry['recruiters'])} recruiter")
            if entry["peers"]:
                types.append(f"{len(entry['peers'])} peer")
            if entry["others"]:
                types.append(f"{len(entry['others'])} other")
            type_str = ", ".join(types)
            f.write(f"| {entry['company']} | {entry['total']} | {type_str} | Add to watchlist.json |\n")

        f.write("\n---\n\n")
        f.write("## All Companies (Full List)\n\n")
        f.write("| Score | Company | Contacts | Recruiters | Peers | Watchlist |\n")
        f.write("|-------|---------|----------|------------|-------|-----------|\n")
        for entry in priority_list:
            wl = "yes" if entry["in_watchlist"] else ("tier1" if entry["is_tier1"] else "")
            f.write(f"| {entry['score']} | {entry['company']} | {entry['total']} | {len(entry['recruiters'])} | {len(entry['peers'])} | {wl} |\n")

    print(f"Written: {output_path}")
    return output_path


def write_outreach_candidates(priority_list: list):
    """
    Write a CSV ready to paste into outreach-tracker.csv.
    One row per contact at a high-priority company.
    Message column left blank — fill in using /tailor or message templates.
    """
    output_path = os.path.join(REPO_ROOT, "outreach_candidates.csv")
    today = date.today().isoformat()
    follow_up = date.today().replace(day=min(date.today().day + 7, 28)).isoformat()

    fieldnames = ["date", "person", "company", "platform", "status",
                  "follow_up_date", "message", "notes"]

    high_priority = [e for e in priority_list if e["score"] >= 40]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for entry in high_priority:
            priority_contacts = entry["recruiters"] + entry["peers"]
            for c in priority_contacts:
                writer.writerow({
                    "date": today,
                    "person": c["name"],
                    "company": entry["company"],
                    "platform": "LinkedIn",
                    "status": "Sent",
                    "follow_up_date": follow_up,
                    "message": "",
                    "notes": f"{c['position']} | score={entry['score']} | type={c['type']}",
                })

    print(f"Written: {output_path}")
    return output_path


def print_summary(priority_list: list, total_connections: int, watchlist: set):
    high = [e for e in priority_list if e["score"] >= 40]
    medium = [e for e in priority_list if 20 <= e["score"] < 40]
    print(f"\n{'='*60}")
    print(f"LINKEDIN CONNECTIONS ANALYSIS")
    print(f"{'='*60}")
    print(f"Total connections: {total_connections}")
    print(f"Unique companies:  {len(priority_list)}")
    print(f"High priority (≥40): {len(high)} companies")
    print(f"Medium priority (20-39): {len(medium)} companies")
    print(f"\nTop 10 outreach targets:")
    for e in priority_list[:10]:
        wl = " [watchlist]" if e["in_watchlist"] else (" [tier1]" if e["is_tier1"] else "")
        r = f" {len(e['recruiters'])}R" if e["recruiters"] else ""
        p = f" {len(e['peers'])}P" if e["peers"] else ""
        print(f"  {e['score']:3d}  {e['company'][:35]:<35}{wl}{r}{p}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Analyze LinkedIn connections for outreach")
    parser.add_argument("--csv", default=os.path.join(REPO_ROOT, "Connections.csv"),
                        help="Path to LinkedIn Connections.csv export")
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        print(f"ERROR: {args.csv} not found.")
        print("Download your LinkedIn data: Settings → Data Privacy → Get a copy of your data")
        print("Select 'Connections', request archive, download CSV, place in this directory.")
        sys.exit(1)

    print(f"Reading {args.csv} ...")
    connections = parse_connections_csv(args.csv)
    print(f"Loaded {len(connections)} connections.")

    watchlist = load_watchlist_companies()
    clusters = cluster_by_company(connections)
    priority_list = build_outreach_priority_list(clusters, watchlist)

    print_summary(priority_list, len(connections), watchlist)
    write_analysis(priority_list, len(connections), watchlist)
    write_outreach_candidates(priority_list)

    print("Next steps:")
    print("  1. Review connections_analysis.md for high-priority contacts")
    print("  2. Add missing Tier 1 companies to watchlist.json")
    print("  3. Personalize outreach_candidates.csv message column")
    print("  4. Paste rows into outreach-tracker.csv once messages are sent")


if __name__ == "__main__":
    main()
