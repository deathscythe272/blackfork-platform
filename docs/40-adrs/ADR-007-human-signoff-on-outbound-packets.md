# ADR-007 — A person signs every packet that leaves, and no agent can

**Status:** accepted
**Serves:** C3, BR-7
**Date:** 2026-09-08

## Context

Auditors and assessors require human-readable trails and human sign-off on what they
receive (C3). The platform's agents draft statements, score findings, and assemble
packets; the question is where the person stands. Sign-off that is a checkbox an
agent can tick is no sign-off, and sign-off that happens after export is a
formality. The threat model asks that a compromised agent's reach stop short of
anything that leaves the boundary (BR-7, BR-8).

## Decision

Every packet is a draft until a person signs it, and only a signed, unchanged packet
can be exported. The rule is enforced in three places that agree. Tokens carry a role
claim, `agent`, `caller`, or `person`; the agent service mints every job token with
`agent`, and only a person's own tooling mints `person`. The signing route refuses any
token whose role is not `person`, and records the refusal like any other. The packet
store checks the role again before it writes a signature, and the signature records
who, when, and the hash of exactly what was signed; export compares that hash to the
packet as it is now and refuses if anything changed. The Report Writer itself writes
no prose: its sentences are the mapper's and its verdicts the analyst's, and any
sentence that cites neither a row nor a control is dropped and counted, so the packet
carries its own measure of how much of it is unsupported.

## Consequences (including what we gave up)

- A compromised agent, any agent, cannot make a packet leave: it cannot sign, and an
  unsigned packet has no export.
- A packet edited after signature is not the signed packet, and the export says so.
- The person signs a document that cites its evidence sentence by sentence, and the
  citations are checkable through the same door the agents used.
- Given up: any fully automated delivery. That is the point, and the business asked
  for it.
- Given up: prose the writer could have added for readability. Readability comes
  from the mapper's statements; anything uncited is not worth the risk of being
  believed.

## Alternatives considered

- **Sign-off as a review step in a workflow tool.** The signature would live outside
  the platform's record and the hash would not bind it to the content.
- **Let the Report Writer sign when every verdict is low.** A rule an attacker only
  has to satisfy once; C3 asks for a person, not a threshold.
- **Export drafts marked "draft".** Marks get lost; a refused export does not.
