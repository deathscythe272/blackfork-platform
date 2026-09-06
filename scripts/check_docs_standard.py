#!/usr/bin/env python3
"""Deterministic check: any doc that opts into the template (contains a
'You are here:' breadcrumb) must carry the required sections of
docs/DOCS-STANDARD.md. This is Gatehouse's earliest ancestor (G1 seed, BR-4)."""
import pathlib
import re
import sys

# Section headings every template doc must carry, matched at line start.
REQUIRED = ["## The 30-second version", "## How it works", "## Why it's built this way"]

failures = []
for path in sorted(pathlib.Path("docs").rglob("*.md")):
    text = path.read_text(encoding="utf-8")
    if "You are here:" not in text:
        continue  # not a template doc (e.g., business case, narrative)
    missing = [s for s in REQUIRED if not re.search(r"^" + re.escape(s), text, re.M)]
    if missing:
        failures.append((path, missing))

if failures:
    for path, missing in failures:
        print(f"FAIL {path}: missing {', '.join(missing)}")
    sys.exit(1)
print("docs standard: OK")
