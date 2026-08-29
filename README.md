# Blackfork Platform

**An agentic security & compliance platform, built as a portfolio project** — from
business problem → requirements → architecture → working code.

Two systems for a fictional company (Blackfork Systems):

- **Provenance** — an evidence lakehouse + GRC agent team: security telemetry in,
  continuously collected, control-mapped, human-signed audit evidence out.
- **Gatehouse** — an AI merge gate: deterministic policy checks that block, plus a
  measured LLM judge for design quality, on every pull request of this very repo.

**Stack:** NVIDIA NeMo Agent Toolkit · NIM · NeMo Guardrails · Garak · MCP · A2A ·
OPA/Rego · Apache Iceberg · DuckDB · Dagster · OSCAL · GCP (Terraform, Cloud Run,
Workload Identity Federation) — everything as code.

➡️ **Start here:** [`docs/00-START-HERE.md`](docs/00-START-HERE.md) — the two-minute tour,
with reading paths for 5 minutes, 15 minutes, or a deep dive.

## Status & roadmap (docs-first phase)

- [x] Business case with measurable requirements (BR-1…BR-7)
- [x] Architecture diagrams (v1) + narrative with ADR map
- [x] Documentation standard + Foundation docs (F1)
- [x] CI enforces the docs standard on every PR — Gatehouse's first deterministic gate
- [ ] Diagram rework for linear readability (v2)
- [ ] Foundation IaC: Terraform modules, WIF keyless CI (F2–F3)
- [ ] Provenance: data plane → context plane → agent plane → assurance plane (P1–P4)
- [ ] Pipeline Steward agent (P5)
- [ ] Gatehouse: judge lane + trust machinery (G2–G3)

## Honest framing

Blackfork Systems is fictional; the engineering is real. This repo exists to demonstrate
working backwards from business requirements to a governed, observable, agent-native
platform — and to be read. Docs follow a screenshare-ready standard
([`docs/DOCS-STANDARD.md`](docs/DOCS-STANDARD.md)).
