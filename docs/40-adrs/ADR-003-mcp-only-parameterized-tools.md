# ADR-003 — MCP is the only path to data, and every tool is parameterized

**Status:** accepted
**Serves:** BR-7, BR-8
**Date:** 2026-09-07

## Context

Agents need to read evidence, control catalogs, and eventually each other's outputs.
There are many ways to give a program access to data: a database connection string,
a shared filesystem, a general-purpose query tool, an HTTP API with a search endpoint.
Each of those is fine for code. None is fine for an agent, for three reasons that the
V1 slice made concrete.

1. **The agent's requests are written by a model that reads untrusted text.** A log
   line, a scanner finding, or an evidence row can carry instructions. If the agent
   holds a tool that accepts a free-form query, an injected instruction becomes a
   query. The slice's poisoned evidence row (ev-0009) is the standing example.
2. **Policy can only decide what it can see.** The gateway (ADR-001) asks the policy
   engine whether *this identity* may call *this tool* with *these arguments*. That
   question has a crisp answer only when the tool's arguments are a small, typed set.
   "May this identity run this SQL string?" has no crisp answer.
3. **Audit is only useful if a row is readable.** An audit row that says
   `get_evidence(system_id=sys-windrow-prod, control_id=3.3.1)` is evidence an
   assessor can read. A row containing a 400-character query is not.

Model Context Protocol (MCP) is the open standard for exposing tools to agents with
declared, typed schemas. It is the natural fit, but the decision here is stronger than
"use MCP": it is that MCP is the *only* door, and that what stands behind the door is a
short list of named, parameterized operations.

## Decision

1. **Agents reach data only through MCP servers, and only through the gateway.**
   No agent holds a database credential, a bucket path, a filesystem mount, or a
   direct network route to a data service. The slice enforces this with network
   placement: the agent container cannot resolve the evidence server's name.
2. **Every tool is a named operation with a typed schema.** Tools take identifiers
   and small enumerations, never free text that is passed through to a query engine.
   There is no `run_sql`, no `search(query)`, no `read_file(path)` tool anywhere in
   the platform.
3. **Every data tool takes `system_id`.** Scope is an argument the policy engine can
   see and constrain, not a side effect of which rows happen to match. A tool that
   cannot be scoped by system is not added.
4. **Servers own their queries.** The SQL, filters, and limits live inside the server
   as code, reviewed through Gatehouse. The model chooses which operation and which
   identifiers; it never composes the query.
5. **Tool lists are small and grow by pull request.** Adding a tool means adding a
   schema, a query, a policy grant, and an eval case, in one reviewed change.

In the slice this is three tools on `evidence-mcp`: `list_controls(system_id)`,
`get_evidence(system_id, control_id, limit)`, and `get_evidence_row(system_id, row_id)`.
The gateway mirrors the same three; the policy grants them per identity per system.

## Consequences (including what we gave up)

- **Injection cannot become a query.** The worst an injected instruction can do is
  make the agent call an allowed tool with allowed identifiers, which the audit log
  records and the policy engine bounds. This is what makes the containment claims in
  the threat model testable (BR-8, tests T1-GW-06 and T1-EV-02).
- **Policy and audit are legible.** Grants are lists of tools and systems; audit rows
  are a handful of named fields. An assessor can read both without a query language.
- **Semantic search is a tool, not a query.** NeMo Retriever (roadmap phase 7) will be
  exposed as `find_related(system_id, text, top_k)` with the retrieval logic inside the
  server. The agent supplies text to embed, not a query to execute, and the result is
  still scoped by system.
- **We gave up flexibility.** An analyst with a database client can ask anything. An
  agent here can ask only what a tool was written for. New questions mean new tools,
  and that is a feature: every capability the agent has is one a person reviewed.
- **We gave up some model cleverness.** A model that could write queries might answer
  an unusual question in one step. Ours may need two or three tool calls, or may have
  to say it cannot. The workload profile (phase 5) will measure the cost of that.
- **Tool sprawl is the new risk.** Small tools multiply. The mitigation is the rule
  that every tool arrives with a policy grant and an eval case, and that the tool
  list is on the end-state map so it stays visible.

## Alternatives considered

| Alternative | Why not |
|---|---|
| **A general query tool with a validator.** Let the model write SQL; parse and reject anything dangerous. | Validators for a query language are never complete, and the policy question ("may this identity run this?") stays unanswerable. Every injected instruction becomes a validator bypass attempt. |
| **Direct database access with row-level security.** Give each agent a database role scoped to its system. | Moves scope enforcement into the database, out of the gateway's audit path, and requires agents to hold credentials. Row-level security also says nothing about *which* operations are allowed. |
| **Read-only files or object storage.** Mount Gold tables read-only and let the agent query with DuckDB in-process. | No per-call policy, no per-call audit, and the agent process becomes the data boundary. A steered agent reads everything it can mount. |
| **A REST API per data source.** Conventional endpoints with authentication. | Workable, but every source invents its own contract and the agent needs bespoke client code per source. MCP gives discoverable, typed tools with one client, and the gateway can front all of them the same way. |
| **MCP with a free-form search tool alongside the fixed ones.** Keep the fixed tools but add one flexible escape hatch. | One free-form tool undoes the guarantee for all of them. If the escape hatch exists, the injected instruction targets it. |

## Relationship to other decisions

- **ADR-001** puts the gateway in front of every MCP server. This decision is what
  makes the gateway's policy question answerable.
- **ADR-004** (planned) isolates the Risk Analyst behind agent-to-agent auth; its
  interface is also a small set of typed operations, for the same reasons.
- **ADR-006** (planned) redacts before storage, so what the tools return carries no
  personal data even when the tool is used as intended.
