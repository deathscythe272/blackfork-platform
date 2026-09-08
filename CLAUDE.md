# CLAUDE.md — Blackfork Platform

## What this project is

Portfolio repo proving Jeff can take an agentic security platform from business
requirements → architecture → working code. Aimed at two NVIDIA roles:

- **PRIMARY — a senior solutions-architect role in agentic AI safety & security:**
  agent safety, guardrails, red-teaming, release-gating evals, secure tool use,
  reference architectures.
- **SECONDARY — a senior software-engineer role in agent architecture & evaluation:**
  agent building, eval rigor, workload analysis; open-source agentic projects count.

Emphasis order: agent safety/security and evaluation rigor first; data-engineering
depth is secondary. The customer (Blackfork Systems) is fictional; the engineering is
real. Two systems: **Provenance** (evidence lakehouse + four GRC agents behind ONE MCP
door with a custom auth gateway) and **Gatehouse** (PR merge gate: deterministic lane +
measured LLM judge — it gates THIS repo). The repo is meant to be *read* and
screenshared as much as run.

## Read before doing anything

1. `docs/00-START-HERE.md` — two-minute tour
2. `docs/01-business-case.md` — BR-1…BR-9 and C1…C4; everything cites these. BR-8
   (agent safety) and BR-9 (evaluation rigor) are the ones the safety work items serve
3. `docs/02-architecture/architecture-narrative.md` — what + why per stage, design
   principles, ADR map
4. `docs/DOCS-STANDARD.md` — doc template + diagram rules (CI-enforced)
5. `docs/ROADMAP.md` — the phased build plan; work items and "done" per phase

## Non-negotiable working rules

- **PR-only flow.** All work on feature branches; never push to `main` directly. Every
  PR fills the template and cites the BR it serves. Remote: `deathscythe272/blackfork-platform`;
  `main` is protected and the docs-standard check is required, admins included.
- **Conventional commits**, small and scoped: `type(scope): message`. Never backdate,
  rewrite published history, or fabricate activity — the honest iterative record is part
  of the portfolio.
- **Docs standard is law.** Template docs keep their required sections and the
  mechanical diagram rules (`scripts/check_docs_standard.py` enforces both); every PR
  body cites a requirement (`scripts/check_pr_body.py` enforces). Code and docs change
  together.
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
  NeMo Guardrails wraps agent I/O; Garak red-teams our own agents and NeMo Auditor
  scores their outputs; command-running agents (Pipeline Steward) execute in a sandbox
  (OpenShell where available, locked container otherwise); NeMo Retriever +
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
  P4 assurance plane · P5 pipeline steward · P6 cartographer (candidate: draws the
  platform's own diagrams from state, reviewed by a redaction lane + the judge).
- **Gatehouse:** G1 deterministic lane (seed exists: `check_docs_standard.py`) · G2
  judge lane · G3 trust machinery (planted-flaw evals, advisory→blocking promotion,
  fail-open/-closed per ADR-005) · G3+ seeded injection evals (below).
- **V1 vertical slice:** one agent end-to-end locally — agent + `evidence-mcp` +
  auth gateway + Guardrails + one golden eval + OTel trace.

## Safety & evaluation work items (serve BR-8, BR-9, C5, P7)

- **T1 — Agent-runtime threat model.** STRIDE the agent platform itself (prompt
  injection, jailbreaks, tool-based data exfiltration, unsafe tool invocation,
  model/skill supply-chain risk, sandbox escape for command-running agents) as
  `docs/02-architecture/agent-threat-model.md` per the docs standard; every threat maps
  to its mitigation (gateway, OPA, parameterized tools, Guardrails, sandbox, audit) AND
  to a planned test.
- **G3+ — Seeded injection evals.** Extend Gatehouse trust machinery with deliberate
  prompt-injection and tool-abuse attempts in the eval sets; publish results so
  containment is a measured claim, not an assertion.
- **W1 — Workload profiling, two workloads.** (a) Our agents via OpenTelemetry + NAT
  profiling → `docs/analysis/agent-workload-profile.md`: token counts, tool-call
  counts, latency distributions, long-horizon behavior, charts committed. (b) The
  coding-agent harness that builds this repo → `docs/analysis/coding-agent-harness-profile.md`:
  per-turn tokens, context growth, tool-call mix, retries, where inference time goes;
  method stated so it repeats on another harness.
- **ADR-008 appendix.** Confidential / air-gapped deployment pattern, explicitly
  labeled design-only (no GPU confidential computing on free tier).

## Build order

diagrams v2 → ADR-001 → **V1 vertical slice** → T1 threat model → G2 judge lane →
G3 incl. injection evals → W1 profiling → F2/F3 Terraform + CI → P1–P4 widen →
ADR-008 appendix → satellites (patterns repo; upstream PRs to NVIDIA repos as habit).

## Current state (2026-09-06)

Docs-first phase complete: business case carries BR-8/BR-9 and C5/P7, START HERE
and the narrative lead with the assurance layer, the three architecture pages read
left to right in parts with walkthroughs, and `docs/ROADMAP.md` holds the phased plan.
Docs-standard CI gate live and required on protected `main`; ADR-001 (gateway) and
ADR-003 (MCP-only) accepted; threat model at `02-architecture/agent-threat-model.md`.
Gatehouse judge (`src/gatehouse/`, NAT plugin `gatehouse_judge`, rubric v1) runs as an
advisory Actions workflow on every PR with the built-in token; `NVIDIA_API_KEY` is a
repository secret. Rubric v1.2: R3, R7, R8 are Lane 1 scripts; judged items R1, R4,
R5, R6 clear every fixture threshold (1.00/1.00); R2 on notice. Required checks on
main: `check` (docs standard incl. diagram rules), `cites-requirement`, `rego`
(policy tests), `boundaries`, and `terraform-plan`. Seeded attacks done: zero steer-induced changes on three judge twins;
seven agent cases contained with zero foreign calls; every answer scored safe; Garak
run on the model; threat model 21/39 passing (B8 added in phase 6). Phase 4 complete except promotion.
Phase 5 done: harness profile (914 turns, 43k→853k context) and agent profile via the
logging proxy (`src/profiling/`); agent tool-call cap 6; Steward token budget 50k/job.
Rubric v1.4: R6 and R9 (boundary change needs a threat-model change) are Lane 1 scripts
in `scripts/check_pr_boundaries.py`, required check `boundaries`; R4 is human review;
the judge scores only R1 and R5. Pass 6: R1 clears every fixture threshold; R5 has one
steer change on a borderline identifier; run success 0.68, all rate limits. The scoring
harness gives each judge call its own trace file (a leaked exporter path had been
failing later calls; pass 5's "timeouts" were mostly that). V1 slice runs locally under `src/provenance/`
(evidence-mcp, gateway with OPA + audit, Evidence Collector on NAT with Guardrails,
OTel, three evals passing; `scripts/demo.py`). Model: nvidia/nemotron-3.5-lightning-30b-a3b
with `chat_template_kwargs.enable_thinking=false`. Phase 6 done (Terraform plan on PR, apply on main, keyless; gateway and evidence server on Cloud Run at scale to zero, agent token in X-Agent-Token, audit to Pub/Sub, budget alert): GCP project (by hand, billing linked) plus `infra/` bootstrap, plane modules, and the dev root; project id lives only in ignored tfvars and a repository variable. Public docs describe the safety and evaluation emphasis without naming job
requisitions. Repo is public on GitHub.

## Immediate queue

1. PR: judge retry waits longer on a rate limit (429) so run success measures the
   endpoint, not a two-second backoff; then re-score. Serves: BR-9.
2. First promotion decision, by PR, once an item has 20 live instances and meets every
   ADR-005 threshold; R1 and R5 are the only candidates left in Lane 2. Live counts:
   `python -m gatehouse.evals.harvest` (rewrites the analysis page block).
4. Phase 7 P1 data plane (Dagster, Iceberg on the lakehouse bucket, DuckDB, Presidio).
