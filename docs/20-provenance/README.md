# Provenance — The Pages

Provenance is the evidence system: rows in, redacted and shaped, served to narrow
agents through one guarded door. One page per plane as each is built; design for the
whole lives in `../02-architecture/` (flow and narrative) and the build order in
`../ROADMAP.md`, phase 7.

- `v1-slice.md` — the running slice: one agent, the gateway, the evidence server,
  guardrails, seven evals, a trace; on a laptop and on Cloud Run.
- `data-plane.md` — evidence in, redacted before storage, served from a narrow table
  any reader can open without a catalog. ADR-002, ADR-006.
- `context-plane.md` — one gateway, two servers: evidence for a system, controls for a
  framework, each a fixed set of questions; the catalog's injection surface and its test.
- `agent-plane.md` — agents as a service: a signed-token door with a quota per caller,
  a job-long token for the agent's own identity, a record per job; the Control Mapper.
- `assurance-plane.md` — after every apply and every night, every agent's cases run
  against the deployed services, scored for containment and safety, compared to the
  last record, recorded where a run cannot erase a run.
- Pipeline Steward — with phase 7.
