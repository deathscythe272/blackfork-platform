# Architecture Narrative — The Life of One Piece of Evidence, and Why

> Companion to the diagrams in `docs/02-architecture/`. Read this alongside
> `03-provenance-architecture` — the step numbers here match the numbers on the diagram.
> Requirements (BR-x) and constraints (C-x) refer to `01-blackfork-business-case.md`.

## The story in one paragraph

A Suricata alert fires on the Security Onion sensor. Fourteen steps later, a sentence in
a draft System Security Plan cites that alert — by row, with a timestamp — as evidence
that a monitoring control is operating. Everything between those two moments is designed
around one bet: **chain of custody**. Every claim in the final packet can be walked
backward through Gold, Silver, and Bronze to an untouched original record, and every
automated action along the way is itself logged, policy-checked, and reviewable. The
system doesn't ask an auditor to trust an AI; it hands them a trail.

---

## Stage 1 — Sources (steps 1a–1e)

**What happens.** Five feeds land raw security facts: network detections from Security
Onion (Zeek + Suricata), the cloud's own account of who did what (GCP audit logs),
software risk from container scanners (Trivy/Grype CVE findings plus SBOMs), the
deployed-infrastructure truth (Terraform state), and adjudicated exploitability verdicts
from the NVIDIA vulnerability-analysis blueprint.

**Why this way.** Compliance evidence must come from *systems of record*, not humans
with screenshot tools — screenshots are point-in-time assertions nobody can verify,
which is exactly the failure in P5 and the reason BR-2 exists. These five feeds were
chosen because together they cover the control families auditors probe hardest —
monitoring, access, vulnerability management, configuration management — using entirely
free and open tooling (C4). The blueprint deserves special mention: we ingest its
*verdicts* rather than raw CVE lists because a CVE count is noise and an exploitability
judgment is signal (BR-6) — and because composing with a vendor's proven agent workflow
beats rebuilding it. Buy the commodity; build the differentiator.

## Stage 2 — Pipelines (steps 2, 4, 6)

**What happens.** Dagster runs scheduled ingest jobs (2). Presidio strips personal data
before anything is stored long-term (4). Asset checks act as a quality gate that stops
bad data loudly (6). When a job breaks, the Pipeline Steward agent — failure path only —
diagnoses the cause and opens a fix PR.

**Why this way.** An orchestrator, not cron: evidence must be *continuous* and
*lineage-tracked*. Cron can run a script; it cannot answer "where did this number come
from, and when" — Dagster's asset lineage can, and that answer is chain of custody
(BR-2). Redaction happens *before* long-term storage because data minimization is the
only PII control that cannot fail later: you can't leak what you never kept, and an
agent-accessible store full of personal data multiplies every downstream risk (BR-7,
C2). The quality gate fails loudly because a wrong audit packet is worse than a late
one — bad evidence discovered by an auditor destroys trust in *all* the evidence.
The steward is an agent because a three-person security team can't babysit pipelines
(C1) and failure diagnosis is pattern work agents do well — but it opens PRs instead of
pushing fixes, because reversibility and human review are requirements (BR-7), not
courtesies.

## Stage 3 — Lakehouse (steps 3, 5, 7)

**What happens.** Data lands raw in Bronze (3), cleaned and redacted in Silver (5), and
is served as narrow, documented Gold views — evidence, assets, findings, control
status — built for agent consumption (7). Tables are Apache Iceberg; queries run through
DuckDB.

**Why this way.** Bronze keeps the untouched original so any claim can be *replayed*: if
a transform ever had a bug, history can be reprocessed, and an assessor can trace a Gold
row back to the exact record as received — forensic integrity. Iceberg over a
proprietary warehouse for three reasons: time travel makes "show me what you knew on
June 3rd" — a literal audit question — a one-line query; an open table format on plain
object storage costs almost nothing (C4); and no engine lock-in means DuckDB today,
Spark or Trino tomorrow, same tables. Gold views are deliberately *narrow*: agents are
more accurate and more governable against small, stable, documented schemas than against
sprawling raw tables. Shaping context for the consumer is a design act — this is what
"agent-ready data" means in practice.

## Stage 4 — MCP access layer (steps 8–9)

**What happens.** Two MCP servers expose the platform's knowledge: `evidence-mcp` offers
safe, parameterized queries over Gold views only (8a); `controls-mcp` serves NIST
800-171 and SOC 2 catalogs in machine-readable OSCAL (8b). Every request from every
agent passes through a custom auth gateway (9) that verifies identity, obtains an OPA
policy decision, and writes the call to the audit table.

**Why this way.** MCP is the *only* door on purpose: if agents can reach data through
side channels, governance is theater. One protocol creates one choke point where
identity, policy, and logging can actually live — which is what makes BR-7 physically
true. MCP specifically because it's the open standard: tools are discoverable,
documented, and swappable, which is what "structured and scalable" integration means.
Queries are parameterized rather than model-written SQL because hallucinated or injected
SQL is an injection attack with extra steps — the schema of what an agent *may* ask is
part of the security boundary. Controls live in their own server because reference
catalogs change on a different cadence than evidence, and in OSCAL because
machine-readable catalogs are what let one evidence row satisfy two frameworks at once
(BR-5) — a spreadsheet mapping cannot do that reliably. The gateway is custom because
the agent toolkit's MCP front-end does not yet ship server-side authentication; rather
than accept an open door, we put a thin, boring, auditable layer in front of it. That
gap-and-response is documented as ADR-001, because recognizing a framework's limits and
architecting around them *is* the job.

## Stage 5 — Agents (steps 10–13)

**What happens.** Four NeMo Agent Toolkit workflows run in sequence: the Evidence
Collector gathers proof per control (10); the Control Mapper links evidence to controls
and drafts implementation statements (11); the Risk Analyst — running as a *separate
service* reached over the A2A protocol with its own authentication — scores and
prioritizes (12); the Report Writer assembles the packet (13).

**Why this way.** Four narrow agents instead of one capable generalist because narrow
agents are testable (each gets its own eval set), debuggable (each gets its own traces),
and independently improvable — a mega-agent fails opaquely and improves nowhere. The
sequence mirrors how a human GRC analyst actually works — gather, categorize,
prioritize, report — so every handoff is a seam a human can inspect. The Risk Analyst
crosses a real network and auth boundary deliberately: in a real organization, risk
scoring may be owned by a different team on different infrastructure, and the platform
must prove agents can cooperate across *trust* boundaries, not just across function
calls in one process. And all four agents draft; none decide. Judgment stays human (C3).

## Stage 6 — Output (step 14)

**What happens.** A draft audit packet and SSP sections arrive for human review. Every
claim carries a citation to its evidence row. Nothing ships without a person's approval.

**Why this way.** Per-claim citations are the entire point of the system: an assertion
without evidence is what auditors reject today, and a claim with a walkable trail —
sentence → Gold row → Silver → Bronze → original alert — is what they accept.
Human sign-off is non-negotiable because accountability cannot be delegated to a model
(BR-7, C3) — and pragmatically, human review of drafts is where correction data comes
from, which feeds the eval sets that make the agents measurably better.

---

## The always-on eight (◆)

These aren't steps in the journey; they're the conditions under which the journey is
allowed to happen.

| Component | Why it exists |
|---|---|
| **NVIDIA NIM endpoints** | Reasoning is rented, not built. Hosted endpoints are free at dev scale, and the same models ship as self-hostable containers — which is the required path the moment CUI enters the boundary (C2). Hosted↔self-hosted is a config change, not a redesign. |
| **NeMo Retriever + Milvus** | SQL answers "what is"; semantic search answers "what's *related*." Mapping evidence to controls needs both — a control's language rarely matches a log's language. |
| **NeMo Guardrails** | Agents read text produced by scanners, logs, and external advisories — that is untrusted input. Rails filter both directions, shrinking the prompt-injection surface. |
| **OPA policies (Rego)** | Policy lives as versioned, testable code *outside* the agents, so the security team changes the rules without redeploying anything — and every decision is reproducible. |
| **Audit table** | The automation must produce evidence about itself. "Why should we trust the robot's evidence?" is the first assessor question; an immutable action log is the answer (BR-7). |
| **OpenTelemetry → Grafana** | You cannot optimize or debug what you cannot see. Per-step latency and cost is how "supports real-time workloads" becomes a measured claim instead of a hope. |
| **Eval harness** | LLM behavior drifts with every model and prompt change. Golden question sets turn "seems fine" into a score — regression testing for judgment. |
| **Garak red-team** | A security platform that has never been attacked is untested. We run NVIDIA's LLM vulnerability scanner against our own agents and publish the findings — and fixes. |

---

## Gatehouse — the same philosophy, pointed at code review

Gatehouse gates this repository's own pull requests with two lanes. Lane 1 is
deterministic and blocking: presence rules (code changed → diagram and threat model must
change too, BR-4) and policy-as-code (e.g., password minimum length ≥ 15 per NIST SP
800-63B rev. 4), each failure citing the exact rule and standard. Lane 2 is an LLM judge
scoring design quality against a versioned rubric — STRIDE coverage, trust boundaries,
data-flow completeness — and it is *advisory until measured*: every rubric item is
graded against a planted-flaw eval set, and only checks whose precision earns it get
promoted to blocking. **Why:** never ask a model to do a parser's job, never ask a
parser to make a judgment call, and never give probabilistic checks veto power they
haven't statistically earned (BR-3, BR-7). Gatehouse's own decisions flow into
Provenance as evidence — the gate is also a sensor.

---

## Design principles (the why, compressed)

1. **Evidence over assertion.** Every claim traces to a system of record; screenshots
   are not evidence.
2. **One door for data.** All agent access goes through MCP behind the gateway.
   Ungoverned paths don't get governed later — they don't get built.
3. **Deterministic before probabilistic.** Exact rules run first, cheaply, and can
   block. Models judge what rules can't express — and advise until measured.
4. **Narrow agents, visible seams.** One responsibility per agent, human-inspectable
   handoffs, per-agent evals and traces.
5. **The automation must survive audit.** Agents are logged, policy-checked, traced,
   eval-scored, and red-teamed like any other production system.
6. **Humans sign.** Agents draft and cite; accountability stays with people.
7. **Rent the commodity, build the differentiator.** Hosted models, open-source
   infrastructure — custom effort goes only where it creates proof: the gateway, the
   policies, the evals.

---

## Where the whys become ADRs

Each load-bearing decision above gets formalized as an Architecture Decision Record,
citing the requirement it serves.

| ADR | Decision to record | Serves |
|---|---|---|
| ADR-001 | Custom auth/audit gateway in front of the MCP server (framework lacks server-side auth) | BR-7 |
| ADR-002 | Iceberg lakehouse with bronze/silver/gold over a proprietary warehouse | BR-2, C4 |
| ADR-003 | MCP as the sole data path; parameterized tools, never model-written SQL | BR-7 |
| ADR-004 | Four narrow agents; Risk Analyst isolated behind A2A with its own auth | BR-3 (velocity via testability), JD-critical |
| ADR-005 | Gatehouse two-lane design; advisory-to-blocking promotion by measured precision | BR-3, BR-4 |
| ADR-006 | Redaction before storage; data minimization as the primary PII control | BR-7, C2 |
| ADR-007 | Human sign-off required on all outbound packets | C3, BR-7 |
| ADR-008 | Hosted NIM for dev, self-hosted NIM containers as the CUI path | C2, C4 |
