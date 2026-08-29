#!/usr/bin/env python3
"""Deterministic check: any doc that opts into the template (contains a
'You are here:' breadcrumb) must carry the required sections of
docs/DOCS-STANDARD.md. This is Gatehouse's earliest ancestor (G1 seed, BR-4)."""
import pathlib
import sys

REQUIRED = ["## The 30-second version", "## Why it's built this way"]

failures = []
for path in sorted(pathlib.Path("docs").rglob("*.md")):
    text = path.read_text(encoding="utf-8")
    if "You are here:" not in text:
        continue  # not a template doc (e.g., business case, narrative)
    missing = [s for s in REQUIRED if s not in text]
    if missing:
        failures.append((path, missing))

if failures:
    for path, missing in failures:
        print(f"FAIL {path}: missing {', '.join(missing)}")
    sys.exit(1)
print("docs standard: OK")
