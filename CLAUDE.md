# CLAUDE.md — Blackfork Platform

## What this project is

Portfolio repo proving Jeff can take an agentic security platform from business
requirements → architecture → working code. Aimed at two NVIDIA roles:

- **PRIMARY — JR2024467, Senior Solutions Architect, Agentic AI — Safety & Security:**
  agent safety, guardrails, red-teaming, release-gating evals, secure tool use,
  reference architectures.
- **SECONDARY — JR2023179, Senior SWE, Agent Architecture & Evaluation:** agent
  building, eval rigor, workload analysis; the JD explicitly values open-source
  agentic projects.

Emphasis order: agent safety/security and evaluation rigor first; data-engineering
depth is secondary. The customer (Blackfork Systems) is fictional; the engineering is
real. Two systems: **Provenance** (evidence lakehouse + four GRC agents behind ONE MCP
door with a custom auth gateway) and **Gatehouse** (PR merge gate: deterministic lane +
measured LLM judge — it gates THIS repo). The repo is meant to be *read* and
screenshared as much as run.

## Read before doing anything

1. `docs/00-START-HERE.md` — two-minute tour
2. `docs/01-business-case.md` — BR-1…BR-7 and C1…C4; everything cites these
3. `docs/02-architecture/architecture-narrative.md` — what + why per stage, design
   principles, ADR map
4. `docs/DOCS-STANDARD.md` — doc template + diagram rules (CI-enforced)

## Non-negotiable working rules

- **PR-only flow.** All work on feature branches; never push to `main` directly. Every
  PR fills the template and cites the BR it serves. Until a GitHub remote exists, PR
  discipline is kept locally: feature branch + `--no-ff` merge commit standing in for
  the PR.
- **Conventional commits**, small and scoped: `type(scope): message`. Never backdate,
  rewrite published history, or fabricate activity — the honest iterative record is part
  of the portfolio.
- **Docs standard is law.** Template docs keep their required sections
  (`scripts/check_docs_standard.py` enforces). Code and docs change together.
- **Diagram rules:** `flowchart LR`, one primary path, ≤7 nodes, every node = name +
  ≤6-word gloss, split into sequential diagrams rather than cramming; time-ordered
  workflows may use sequence diagrams.
- **ADRs for load-bearing decisions** using `docs/40-adrs/TEMPLATE.md`; planned set in
  `docs/40-adrs/README.md`. Never contradict an accepted ADR — supersede it.
- **Secrets never touch the repo.** Env vars locally, GCP Secret Manager deployed;
  NVIDIA key = `NVIDIA_API_KEY`.
- **Cost discipline (C4):** near-zero idle is a requirement. Prefer free tiers and
  local runs; flag anything with meaningful cost before building it.
- **Definition of done:** checks green, docs updated, BR cited, no secrets, diagram
  updated if architecture changed.

## Fixed stack decisions (don't relitigate; supersede via ADR only)

- **Agents:** NVIDIA NeMo Agent Toolkit (`nvidia-nat`). Inference via hosted NIM
  endpoints (free dev tier); self-hosted NIM containers are the CUI path (ADR-008).
  NeMo Guardrails wraps agent I/O; Garak red-teams our own agents; NeMo Retriever +
  Milvus for semantic search.
- **Access:** MCP is the *only* data door, behind a custom auth gateway — identity +
  OPA decision + audit write on every call (ADR-001, ADR-003). Risk Analyst runs as a
  separate A2A service with its own auth (ADR-004).
- **Data:** Dagster → Apache Iceberg bronze/silver/gold on GCS, queried with DuckDB;
  Presidio redaction before silver (ADR-006); control catalogs in OSCAL (NIST 800-171 +
  SOC 2); every evidence row carries `system_id`.
- **Policy:** OPA/Rego, run in CI via Conftest for the deterministic lane.
- **Cloud:** GCP — Cloud Run (scale-to-zero), Pub/Sub, Artifact Registry, Secret
  Manager. Terraform modules mirror the planes; envs `dev`/`demo`. GitHub Actions with
  Workload Identity Federation (keyless): plan on PR, apply on `main` only.
- **Taxonomy labels on everything:** `plane` / `system` / `env` / `serves-br`.

## Chunk map

- **Foundation:** F1 docs spine (done) · F2 cloud substrate (Terraform) · F3 CI/CD.
- **Provenance:** P1 data plane · P2 context plane (MCP + gateway) · P3 agent plane ·
  P4 assurance plane · P5 pipeline steward.
- **Gatehouse:** G1 deterministic lane (seed exists: `check_docs_standard.py`) · G2
  judge lane · G3 trust machinery (planted-flaw evals, advisory→blocking promotion,
  fail-open/-closed per ADR-005) · G3+ seeded injection evals (below).
- **V1 vertical slice:** one agent end-to-end locally — agent + `evidence-mcp` +
  auth gateway + Guardrails + one golden eval + OTel trace.

## Safety & evaluation work items (added 2026-09-04 for the re-aim)

- **T1 — Agent-runtime threat model.** STRIDE the agent platform itself (prompt
  injection, jailbreaks, tool-based data exfiltration, unsafe tool invocation,
  model/skill supply-chain risk) as `docs/02-architecture/agent-threat-model.md` per
  the docs standard; every threat maps to its mitigation (gateway, OPA, parameterized
  tools, Guardrails, audit) AND to a planned test.
- **G3+ — Seeded injection evals.** Extend Gatehouse trust machinery with deliberate
  prompt-injection and tool-abuse attempts in the eval sets; publish results so
  containment is a measured claim, not an assertion.
- **W1 — Agent workload profiling.** Instrument the agents via OpenTelemetry + NAT
  profiling; publish `docs/analysis/agent-workload-profile.md` with measured token
  counts, tool-call counts, latency distributions, and long-horizon behavior, charts
  committed.
- **ADR-008 appendix.** Confidential / air-gapped deployment pattern, explicitly
  labeled design-only (no GPU confidential computing on free tier).

## Build order

diagrams v2 → ADR-001 → **V1 vertical slice** → T1 threat model → G2 judge lane →
G3 incl. injection evals → W1 profiling → F2/F3 Terraform + CI → P1–P4 widen →
ADR-008 appendix → satellites (patterns repo; upstream PRs to NVIDIA repos as habit).

## Current state (2026-09-04)

Ten commits on `main` plus this contract PR; docs-first phase complete; docs-standard
CI gate live; `20-provenance/` and `30-gatehouse/` stubbed; no ADRs written yet; no
infra code yet. No GitHub remote yet — `gh` CLI installed but unauthenticated; branch
protection + required check to be enabled once the repo is pushed.

## Immediate queue

1. This PR: re-aim the contract at JR2024467/JR2023179 (Serves: BR-1).
2. PR: diagram v2 rework to meet the diagram rules (Serves: BR-4) — remove the "v1"
   notes as each is replaced; fix stale cross-references in the narrative.
3. PR: ADR-001 — the MCP auth gateway decision (include a STRIDE sketch of the
   gateway as T1's seed).
4. PR: V1 vertical slice (plan paragraph first — it exceeds an hour).
