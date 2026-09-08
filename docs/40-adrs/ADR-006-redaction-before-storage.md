# ADR-006 — Redaction before storage: no unredacted copy where an agent can reach

**Status:** accepted
**Serves:** BR-7, C2
**Date:** 2026-09-08

## Context

Evidence summaries are written by people and tools, and they carry names, email
addresses, network addresses, and phone numbers. Agents read evidence and put it into
prompts; prompts go to a model endpoint that, on the hosted path, is outside the
customer's boundary (C2). The threat model's B2 row for information disclosure asks
that sensitive data never leave the boundary inside a prompt. Redacting at read time
would satisfy that only if every read path remembered to redact.

## Decision

Redaction happens once, in the pipeline, between bronze and silver, before any row is
stored where an agent can read it. Bronze keeps the original for the record and is not
served. The redactor replaces four entity types with typed labels: people, email
addresses, IP addresses, phone numbers. The set is short on purpose, so the platform's
own vocabulary, control ids, framework names, system ids, is never touched. A check
on silver scans every stored row two ways, with the redactor's detector and with an
independent set of plain patterns, and fails the run if either finds anything. Data
minimization is the primary personal-data control; the output guardrail is the second
line, not the first.

## Consequences (including what we gave up)

- There is no unredacted copy on any path an agent can take. The output rail and the
  gateway's narrow views are belts over braces.
- The check is only as good as its two detectors. The first run proved the point: a
  phone number the language model ignored would have passed a check that used only
  the language model. The pattern layer exists because of that run.
- Given up: the ability to show a person the original summary through the platform.
  That is what bronze is for, and reading bronze is a human operation outside the
  agent path.
- Given up: perfect recall. Names the model does not recognize survive. The entity
  set will widen only with a planted row that proves the gap, never by guess.

## Alternatives considered

- **Redact at read time in the evidence server.** One forgotten path, one new tool,
  and the promise is gone. Storage-time redaction cannot be bypassed by a reader.
- **Redact inside the agent's input rail.** Too late: the row is already in the
  process that builds the prompt, and the rail's job is intent, not data.
- **A wider entity set (locations, organizations, dates).** Tried on the fixture rows;
  it redacted control names and system ids. Widen with evidence, per the rule above.
