#!/usr/bin/env python3
"""Deterministic check, Gatehouse Lane 1: the pull-request body cites an existing
requirement or constraint ("Serves: BR-n" or "Serves: Cn"). Reads the body from the
GitHub event payload in Actions, or from a file path for local use. (BR-4, BR-9)"""
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lane1_rules import citation  # noqa: E402

if len(sys.argv) > 1:
    body = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
else:
    event = json.loads(pathlib.Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    body = (event.get("pull_request") or {}).get("body") or ""

ok, why = citation(body)
print(("pr body: OK, " if ok else "FAIL pr body: ") + why)
sys.exit(0 if ok else 1)
