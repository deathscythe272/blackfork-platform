#!/usr/bin/env python3
"""Deterministic check, Gatehouse Lane 1: a new agent tool ships with a policy grant and
an eval case (R6), and a trust-boundary change ships with a threat-model change (R9), in
the same pull request. Reads the diff against the base ref; no model, no body text.

    python3 scripts/check_pr_boundaries.py origin/main      # base ref
(BR-7, BR-8, BR-9)"""
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lane1_rules import added_lines_from_patch, boundary_rule, removed_lines_from_patch, tool_rule  # noqa: E402

base = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
merge_base = subprocess.run(["git", "merge-base", base, "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
paths = subprocess.run(["git", "diff", "--name-only", merge_base, "HEAD"], capture_output=True, text=True, check=True).stdout.split()
added, removed = [], []
for p in paths:
    patch = subprocess.run(["git", "diff", "--unified=0", merge_base, "HEAD", "--", p], capture_output=True, text=True).stdout
    added += added_lines_from_patch(p, patch)
    removed += removed_lines_from_patch(p, patch)

fails = tool_rule(paths, added) + boundary_rule(paths, added, removed)
for f in fails:
    print("FAIL pr boundaries:", f)
if not fails:
    print(f"pr boundaries: OK ({len(paths)} file(s), {len(added)} added line(s))")
sys.exit(1 if fails else 0)
