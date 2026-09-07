# Agent-Runtime Threat Model

> **In one line:** How the agents themselves get attacked, boundary by boundary, with the control that answers each threat and the test that proves the control works, or the honest word "gap".

**You are here:** START HERE › Architecture › Agent-Runtime Threat Model
**Audience:** 🔴 deep-dive · **Reads in:** ~12 min

## The 30-second version

An AI agent that reads outside text and can reach data or run commands is a new kind of
attack surface. Someone can hide instructions in a log line. Someone can talk the agent
out of its rules. A steered agent can ask for data it should not have, call the wrong
tool, or run a command it should never run. And the model, prompts, and libraries the
agent is built from can be swapped or poisoned before it ever starts. This page draws
the lines an attack would have to cross, lists what could go wrong at each line using a
standard six-part checklist, names the control in the design that stops it, and
names the test that proves the control works. Where no test exists yet, the row says
so. Nothing here is asserted without a test or a labeled gap.

## The picture

**Part 1 — Runtime boundaries.** Every one of these is crossed on every question.

```mermaid
flowchart LR
  USER["Caller<br><i>eval runner or person</i>"] -->|"B1"| AGENT["Agent<br><i>one job, one system, three tools</i>"]
  AGENT -->|"B2"| MODEL["Model endpoint<br><i>hosted NIM, or self-hosted</i>"]
  AGENT -->|"B3"| GW["Gateway<br><i>token, policy, audit, forward</i>"]
  GW -->|"B4"| POLICY["OPA and audit log<br><i>decides and records</i>"]
  GW -->|"B5"| MCP["evidence-mcp<br><i>fixed queries over data</i>"]
```

**Part 2 — Build-time and host boundaries.** Crossed before the agent starts, or only by agents that act.

```mermaid
flowchart LR
  REPO["Repo and supply chain<br><i>prompts, rails, deps, model pin</i>"] -->|"B6"| AGENT["Agent<br><i>same agent as Part 1</i>"]
  AGENT -.->|"B7, agents that act"| HOST["Host<br><i>commands, files, network</i>"]
```

Seven boundaries. B1 through B6 exist in the V1 slice today. B7 is drawn dashed because
no agent in the slice runs commands; it applies to the Pipeline Steward (roadmap phase
7) and is modeled now so the sandbox is a requirement before the first such agent is
built (C5).

## How it works

1. **B1, caller to agent.** Whatever asks the question. Today the eval runner; later a
   person or a scheduled job. Hostile text enters here directly.
2. **B2, agent to model.** Every reasoning step is a network call to a model the
   platform does not control. Prompts go out; completions come back and are trusted as
   the agent's next thought.
3. **B3, agent to gateway.** Every tool call. The agent presents a service token; the
   gateway is the only thing the agent can reach that touches data.
4. **B4, gateway to policy and audit.** The gateway asks the policy engine (Open Policy Agent, OPA) whether the call is allowed
   and writes the decision to an append-only log before forwarding.
5. **B5, gateway to evidence server.** Only the gateway can reach the evidence server;
   the server runs fixed, parameterized queries.
6. **B6, repo and supply chain to agent.** The system prompt, guardrail prompts, policy
   files, dependencies, and model version all arrive from the repo and package indexes.
   A change here changes the agent's behavior without any attacker touching it at
   runtime.
7. **B7, agent to host.** For an agent that runs commands, the boundary between the
   agent and the machine it runs on: filesystem, credentials, network.

Each boundary gets a STRIDE pass below. STRIDE is the six-part checklist used in
threat modeling: spoofing, tampering, repudiation, information disclosure, denial of
service, and elevation of privilege. Test IDs are stable names; the roadmap phase
that implements a planned test is given so a gap has an owner.

## The details

**Status key.** *Passing* means the test exists and passed in the latest run.
*Planned* means the test is specified and scheduled. *Gap* means the design has no
control yet, or the control exists with no test, and the row says which.

### B1 — Caller to agent

| STRIDE | Threat | Control in the design | Test | Status |
|---|---|---|---|---|
| Spoofing | A caller claims an authority the agent should obey ("URGENT from the CISO") | The agent has no notion of caller authority; its assignment is fixed in the system prompt and enforced by policy at B3, not by who asks | T1-IN-01: direct injection eval case `direct-injection-ciso` | Passing, refused at the input rail |
| Tampering | Instructions embedded in the question redirect the agent to another system or tool | Guardrails input rail scores the question against a written policy before the agent sees it | T1-IN-01 | Passing |
| Tampering | Instructions arrive inside data the agent legitimately reads (indirect injection) | System prompt states that evidence text is data; the gateway denies any resulting call for another system regardless | T1-IN-02: `indirect-injection-evidence-row` eval case | Passing, agent did not follow the instruction; gateway backstop covered by T1-GW-06 |
| Information disclosure | The agent is asked to reveal its instructions, token, or the other system's rows | Output rail blocks answers that leak instructions, credentials, or other-system rows | T1-IN-03: eval case asking for the system prompt and token | Planned, phase 4 |
| Denial of service | A caller floods the agent with expensive questions | None in the slice | T1-IN-04: rate limit per caller | Gap, phase 6 (Cloud Run concurrency and quota) |
| Elevation | A caller talks the agent out of its role over several turns (multi-turn jailbreak) | Slice is single-turn; Guardrails dialog rails apply when conversation is added | T1-IN-05: multi-turn jailbreak set from Garak probes | Planned, phase 4 |

### B2 — Agent to model

| STRIDE | Threat | Control in the design | Test | Status |
|---|---|---|---|---|
| Spoofing | Traffic to the model endpoint is redirected to a hostile endpoint | TLS to a pinned base URL; when controlled unclassified information (CUI) is in scope the model runs inside the boundary (architecture decision record ADR-008) | T1-MD-01: endpoint pin check in config validation | Planned, phase 6 |
| Tampering | The model's completion carries a tool call the agent should not make | The agent cannot make a call the gateway does not allow; every completion-driven call still passes B3 | T1-GW-06 | Passing |
| Information disclosure | Sensitive data leaves the boundary inside prompts | Redaction before storage (ADR-006) means Gold rows carry no personal data; agent reads narrow views only | T1-MD-02: prompt payload scan for PII patterns in the trace | Planned, phase 5, using the OpenTelemetry (OTel) spans |
| Denial of service | Endpoint rate limits or outages stall the agent | Retries with backoff in the client; the agent failing is a result the eval runner records, not a crash | T1-MD-03: eval run with the endpoint blocked returns a failed case, not a hang | Planned, phase 4 |
| Elevation | The model is swapped for one with different safety behavior | Model name pinned in config; a model change re-runs the eval set and a regression blocks release | T1-SC-02 | Planned, phase 4 |

### B3 — Agent to gateway

| STRIDE | Threat | Control in the design | Test | Status |
|---|---|---|---|---|
| Spoofing | A forged or replayed token acts as the Evidence Collector | Signed tokens with issuer, audience, and expiry; unknown or invalid tokens are refused before policy runs | T1-GW-01: forged token rejected and audited (`smoke.py`) | Passing |
| Tampering | Arguments altered in transit, or a tool name that does not exist | Tool schema validation by the Model Context Protocol (MCP) server layer; transport is plain HTTP inside a private Compose network today | T1-GW-02: off-schema calls refused | Passing for schema; **gap** for transport (no TLS between containers; phase 6 adds mutual TLS) |
| Repudiation | A call cannot later be tied to an identity and a decision | Audit row per call, denies included, with identity, tool, arguments, decision, policy version, timestamp | T1-GW-03: every eval call appears in the audit log with its decision | Passing, asserted by the eval runner on every case |
| Information disclosure | The gateway logs payloads or results | Gateway logs decisions, not results; audit rows carry arguments only | T1-GW-04: audit and server logs contain no result payloads (`src/provenance/tests/test_boundaries.py`) | Passing |
| Denial of service | A looping agent floods the gateway | None in the slice beyond the agent's `max_tool_calls` | T1-GW-05: per-identity rate limit, other callers unaffected | Gap, phase 6 |
| Elevation | A steered agent requests another system's data or an ungranted tool | Default-deny Rego; grants per identity per tool per `system_id`; no rule allows a call without a `system_id` | T1-GW-06: cross-system and unknown-tool calls denied (`smoke.py`, Rego tests, eval runner) | Passing |

### B4 — Gateway to policy and audit

| STRIDE | Threat | Control in the design | Test | Status |
|---|---|---|---|---|
| Tampering | Policy files altered so a denied call becomes allowed | Policy is code in the repo, reviewed through Gatehouse; OPA mounts it read-only; decision carries the policy version into the audit row | T1-PL-01: Rego unit tests (7) run in CI on every PR (`policy-tests` workflow) | Passing, required check |
| Repudiation | Audit rows altered or deleted after the fact | Append-only file in the slice; the gateway fsyncs each row before forwarding | T1-PL-02: audit hash chain or write-once storage | Gap, phase 7 (audit table in the lakehouse with Iceberg snapshots) |
| Information disclosure | Audit rows reveal sensitive arguments | Arguments are identifiers (`system_id`, `control_id`, `row_id`), never free text | T1-GW-04 | Passing |
| Denial of service | OPA or the audit path is unavailable | Fail closed: the gateway refuses the call | T1-PL-03: stop OPA, confirm calls are refused and nothing is forwarded (`test_boundaries.py`) | Passing |
| Elevation | A default-allow rule slips into policy | `default allow := false` plus a test that an unknown identity is denied | T1-PL-01 | Passing, required check |

### B5 — Gateway to evidence server

| STRIDE | Threat | Control in the design | Test | Status |
|---|---|---|---|---|
| Spoofing | Something other than the gateway calls the evidence server | Evidence server sits on an internal network with no route from the agent or outside | T1-EV-01: from the agent container, the evidence server does not resolve (`test_boundaries.py`) | Passing, automated |
| Tampering | A query is shaped to read outside its scope | No free-form query tool; every tool takes `system_id` and filters on it inside the query | T1-EV-02: `get_evidence_row` with a row from another system returns nothing (`test_boundaries.py`) | Passing |
| Information disclosure | The evidence server returns more than asked | Narrow Gold views; result limit capped at 50 | T1-EV-02 | Passing |
| Elevation | The evidence server has write access to data | Read-only DuckDB connection; data volume mounted read-only | T1-EV-03: write attempt fails (`test_boundaries.py`) | Passing |

### B6 — Repo and supply chain to agent

| STRIDE | Threat | Control in the design | Test | Status |
|---|---|---|---|---|
| Tampering | System prompt or guardrail prompts changed to weaken rules | Prompts are files in the repo; changes go through Gatehouse; eval set re-runs on every change | T1-SC-01: eval run required on any change under `src/provenance/agent/` | Planned, phase 4 (CI job) |
| Tampering | A dependency is swapped or a malicious version pulled | Pinned versions in requirements files; container images built from pinned bases | T1-SC-03: lockfile with hashes, scan in CI | Gap, phase 6 (Trivy on images, hash-pinned requirements) |
| Spoofing | The model name resolves to a different model than intended | Model pinned by name; the hosted catalog retired one model during the build, which is the live example | T1-SC-02: model-change detection re-runs the eval set and a regression blocks | Planned, phase 4 |
| Repudiation | A behavior change cannot be traced to a commit | Every change is a PR citing a requirement; results file committed per run | T1-SC-04: results file diff attached to the PR | Planned, phase 4 |

### B7 — Agent to host, for agents that act

No agent in the slice runs commands. This boundary is modeled now because the Pipeline
Steward will, and C5 says the rules must exist before the first such agent is trusted.

| STRIDE | Threat | Control in the design | Test | Status |
|---|---|---|---|---|
| Elevation | The agent reaches the host filesystem, ambient credentials, or the open network | Sandboxed execution: no host filesystem, no ambient credentials, egress allow-list. OpenShell is the NVIDIA-native runtime; a locked container is the free-tier stand-in. The slice's agent container already has no route to internal services, which is the seed | T1-HX-01: escape attempts in the Steward's adversarial eval set; denied-egress log is the assertion | Planned, phase 7 |
| Tampering | The agent modifies files outside its working tree or pushes directly | The Steward opens pull requests; it has no push right to protected branches | T1-HX-02: Steward credentials cannot push to `main` | Planned, phase 7 |
| Repudiation | A command run by an agent cannot be attributed | Every command logged with the agent identity, in the same audit path as tool calls | T1-HX-03 | Planned, phase 7 |
| Denial of service | A runaway agent consumes host resources | Container CPU and memory limits; wall-clock limit per job | T1-HX-04 | Planned, phase 7 |

### Test index

| Test | Boundary | Where it lives today | Status |
|---|---|---|---|
| T1-IN-01, T1-IN-02 | B1 | `src/provenance/evals/cases.yaml` | Passing |
| T1-IN-03, T1-IN-04, T1-IN-05 | B1 | phase 4 eval set, phase 6 quota | Planned / gap |
| T1-MD-01 to T1-MD-03 | B2 | phase 4 to 6 | Planned |
| T1-GW-01, T1-GW-02, T1-GW-03, T1-GW-06 | B3 | `src/provenance/gateway/smoke.py`, `policy/gateway_test.rego`, eval runner | Passing |
| T1-GW-04 | B3 | `src/provenance/tests/test_boundaries.py` | Passing |
| T1-GW-05 | B3 | phase 6 | Gap |
| T1-PL-01 | B4 | `policy/gateway_test.rego`, `policy-tests` workflow | Passing, required check |
| T1-PL-02 | B4 | phase 7 | Gap |
| T1-PL-03 | B4 | `test_boundaries.py` | Passing |
| T1-EV-01 to T1-EV-03 | B5 | `test_boundaries.py` | Passing |
| T1-SC-01 to T1-SC-04 | B6 | phase 4, phase 6 | Planned / gap |
| T1-HX-01 to T1-HX-04 | B7 | phase 7 | Planned |

Count: 34 threat rows, 16 passing, 13 planned with a phase, 5 gaps named. The gaps are
transport encryption between containers, rate limiting at two boundaries, audit
immutability beyond append-only, and dependency hash pinning.

## Why it's built this way

The requirement is that every threat maps to a mitigation and a test, and that
containment is demonstrated rather than asserted (BR-8). A threat model with only
mitigations is a list of intentions. Giving every row a test ID makes the document a
backlog the eval sets and CI have to satisfy, and marking the rows that are not yet
covered keeps the page honest: a reader can see exactly how much of the design is
proven today and what phase closes each remaining row. The boundaries follow the slice
rather than an idealized system because the slice is what can be attacked (BR-9). B7
is included before any agent needs it because C5 says the rules for agents that act
on infrastructure are written first, not after the first incident.

## Go deeper

**Next:** `../ROADMAP.md` — phases 4 to 7, where the planned tests above get built.

- `../40-adrs/ADR-001-mcp-auth-gateway.md` — the gateway decision whose STRIDE sketch
  this page grows
- `../20-provenance/v1-slice.md` — the running system these boundaries are drawn on
- `architecture-narrative.md` — "What could go wrong" for the short version by threat
  class rather than by boundary
- `../01-business-case.md` — BR-8, BR-9, and C5
