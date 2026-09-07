#!/usr/bin/env python3
"""Deterministic check, Gatehouse Lane 1: any doc that opts into the template
(contains a 'You are here:' breadcrumb) must carry the required sections of
docs/DOCS-STANDARD.md, its diagrams must obey the mechanical diagram rules (left to
right, at most seven nodes, every node glossed), and a single-diagram page's numbered
walkthrough must have one entry per box. The one named exemption is
the end-state map. (G1, BR-4)"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lane1_rules import diagram_rules, walkthrough_rule  # noqa: E402

REQUIRED = ["## The 30-second version", "## How it works", "## Why it's built this way"]

failures = []
for path in sorted(pathlib.Path("docs").rglob("*.md")):
    text = path.read_text(encoding="utf-8")
    if "You are here:" not in text:
        continue  # not a template doc (e.g., business case front matter, ADRs)
    missing = [s for s in REQUIRED if not re.search(r"^" + re.escape(s), text, re.M)]
    if missing:
        failures.append((path, "missing " + ", ".join(missing)))
    for f in diagram_rules(text, path.as_posix()) + walkthrough_rule(text, path.as_posix()):
        failures.append((path, f))

if failures:
    for path, why in failures:
        print(f"FAIL {path}: {why}")
    sys.exit(1)
print("docs standard: OK")
