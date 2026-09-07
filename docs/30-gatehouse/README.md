# Gatehouse — Docs In Progress

Lane 1 runs today as a required check: `scripts/check_docs_standard.py` (G1 seed).
Lane 2, the judge, is documented in `judge-lane.md`: an advisory reviewer on every pull
request with a six-item rubric and a fixed-or-dismissed loop. ADR-005 sets the bar for the
judge to block; `../analysis/judge-precision.md` shows how close each rubric item is,
measured on planted-flaw fixtures. Seeded attacks follow. Flow:
`../02-architecture/gatehouse-pr-flow.md`; build order: `../ROADMAP.md`, phase 4.
