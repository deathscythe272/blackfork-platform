# Blackfork Platform

**An agentic security & compliance platform, built as a portfolio project** — from
business problem → requirements → architecture → working code, with the AI agents
themselves treated as an attack surface to be threat-modeled, tested, and measured.

Two systems for a fictional company (Blackfork Systems), and one layer they share:

- **Provenance** — an evidence lakehouse + GRC agent team: security telemetry in,
  continuously collected, control-mapped, human-signed audit evidence out.
- **Gatehouse** — an AI merge gate: deterministic policy checks that block, plus an
  LLM judge for design quality that earns blocking power only through measured
  precision, on every pull request of this very repo.
- **Assurance** — one guarded door for all agent data access, guardrails on every
  agent, a threat model of the agent runtime, deliberate injection attempts seeded into
  the evals, and published workload profiles.

**Stack:** NVIDIA NeMo Agent Toolkit · NIM · NeMo Guardrails · Garak · NeMo Auditor · MCP · A2A ·
OPA/Rego · Apache Iceberg · DuckDB · Dagster · OSCAL · GCP (Terraform, Cloud Run,
Workload Identity Federation) — everything as code.

➡️ **Start here:** [`docs/00-START-HERE.md`](docs/00-START-HERE.md) — the two-minute tour,
with reading paths for 5 minutes, 15 minutes, or a deep dive.

## Status & roadmap

Phase-by-phase plan with steps and done-criteria: [`docs/ROADMAP.md`](docs/ROADMAP.md).

- [x] Business case with measurable requirements (BR-1…BR-9), including agent safety
      and evaluation rigor
- [x] Architecture pages — context, Provenance flow, Gatehouse flow — each read left to
      right with a numbered walkthrough, plus the narrative with ADR map
- [x] Documentation standard + Foundation docs (F1)
- [x] CI enforces the docs standard on every PR — Gatehouse's first deterministic gate
- [x] Phased roadmap with done-criteria per phase
- [ ] ADR-001: the MCP auth-gateway decision
- [x] V1 vertical slice: one agent end-to-end locally — agent + evidence-mcp + auth
      gateway (OPA, audit) + Guardrails + golden and injection evals + OTel trace
      ([docs/20-provenance/v1-slice.md](docs/20-provenance/v1-slice.md))
- [x] T1: agent-runtime threat model — seven boundaries, every threat with a control
      and a test ID, gaps named ([docs/02-architecture/agent-threat-model.md](docs/02-architecture/agent-threat-model.md))
- [x] Gatehouse: judge lane (G2, advisory on every PR) + ADR-005 + planted-flaw precision
      per rubric item, every pass kept ([docs/analysis/judge-precision.md](docs/analysis/judge-precision.md)),
      and every change of course with its cost ([docs/analysis/adjustments.md](docs/analysis/adjustments.md))
- [x] Seeded attacks: injection twins against the judge, hostile and poisoned cases
      against the agent, Garak against the model, every answer safety-scored
      ([docs/analysis/seeded-attacks.md](docs/analysis/seeded-attacks.md))
- [ ] First promotion of a rubric item to blocking, once 20 live PR instances exist
- [x] W1a: coding-agent harness profile — the agent that built this repo, measured
      from its own logs, aggregates only ([docs/analysis/coding-agent-harness-profile.md](docs/analysis/coding-agent-harness-profile.md))
- [x] W1b: our agents' workload profile — every model call's tokens and latency through
      a logging proxy, plus a twenty-run long-horizon check ([docs/analysis/agent-workload-profile.md](docs/analysis/agent-workload-profile.md))
- [ ] Foundation IaC: Terraform modules, WIF keyless CI (F2–F3)
- [ ] Provenance: widen the planes (P1–P4) + Pipeline Steward (P5)
- [ ] ADR-008 appendix: confidential/air-gapped deployment pattern (design-only)

## Honest framing

Blackfork Systems is fictional; the engineering is real. This repo exists to demonstrate
working backwards from business requirements to a governed, observable, agent-native
platform — and to be read. Docs follow a screenshare-ready standard
([`docs/DOCS-STANDARD.md`](docs/DOCS-STANDARD.md)).
