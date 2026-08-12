#!/usr/bin/env python3
"""
One-time setup: saves your Anthropic API key to ~/.anthropic_key
so evaluate_matches.py can find it without needing environment variables.

Run once:
    python3 setup_key.py
"""

import sys
from pathlib import Path

KEY_FILE = Path.home() / ".anthropic_key"

print("Paste your Anthropic API key and press Enter.")
print("Get it from: https://console.anthropic.com → API Keys")
print()

key = input("API key: ").strip()

if not key.startswith("sk-ant-"):
    sys.exit("That doesn't look right — key should start with sk-ant-")

try:
    key.encode("ascii")
except UnicodeEncodeError:
    sys.exit("Key contains invalid characters. Copy it fresh from the console and try again.")

if len(key) < 80:
    sys.exit(f"Key is only {len(key)} characters — it looks truncated. A full key is ~108 chars.")

KEY_FILE.write_text(key + "\n", encoding="ascii")
KEY_FILE.chmod(0o600)
print(f"\nSaved to {KEY_FILE}")
print("You can now run: python3 evaluate_matches.py --limit 5")
