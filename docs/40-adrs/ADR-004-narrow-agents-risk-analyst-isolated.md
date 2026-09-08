# ADR-004 — Narrow agents, and the Risk Analyst isolated behind its own door

**Status:** accepted
**Serves:** BR-3, BR-8
**Date:** 2026-09-08

## Context

The platform's agents could be one agent with every tool and every job. That agent
would hold the widest grant, read the most, and be the single thing an attacker
needs to steer. The business asks for decisions at speed with a trail behind each one
(BR-3), and the threat model asks that a compromised agent reach as little as
possible (BR-8). The Risk Analyst is the agent that reads the most adversarial input:
statements written by another agent, requirement text, evidence summaries, all of
which can carry planted instructions.

## Decision

Agents are narrow: one job, one identity, one grant. The Evidence Collector gathers;
the Control Mapper drafts statements and holds a grant with no single-row lookup and
no catalog search; the Report Writer assembles and cannot sign. Each runs under a
job-long token for its own identity, minted by the agent service, never held by the
caller.

The Risk Analyst is not narrow, it is isolated. It runs as a separate service with its
own signing key, reached over the agent-to-agent protocol's shape: an agent card that
says who it is and how to authenticate, and a `message/send` that takes a finding and
returns a task with the verdict as its artifact. It has no identity in the gateway's
policy, no gateway address, no gateway token, no bucket, and on Compose no route to any
of them; in the cloud only the agent service's identity may invoke it, and it checks
its own token on top. It can read exactly what the caller hands it. Its score is
deterministic, computed from facts about the evidence; text in the finding is input to
the explanation only, so an instruction planted in a statement cannot move the number.

## Consequences (including what we gave up)

- A compromised analyst can lie in its explanation and nothing else: it cannot reach
  evidence, cannot call tools, cannot change a score. A test proves the door is not
  there to reach.
- A compromised mapper can feed the analyst a false statement; the score still counts
  the rows the statement cites against the rows that exist, so an invented citation
  raises the risk rather than lowering it.
- Cooperation across a real network and authentication boundary is demonstrated, which
  is what the platform must prove before agents from other parties are admitted.
- Given up: one agent that could do everything in one pass, and the convenience of one
  token. Given up: the analyst reading evidence for itself; the caller must assemble
  the finding, which is more code and one more thing the audit trail records.

## Alternatives considered

- **One agent with all tools.** Fewer moving parts, widest blast radius, one prompt to
  steer.
- **The analyst as one more tool behind the gateway.** Simpler transport, but it would
  hold a gateway identity and a grant, which is exactly the reach the isolation exists
  to deny.
- **A model-scored verdict.** More nuanced, and the score would be steerable by the
  text it reads. The deterministic half is the promise; the model explains it.
