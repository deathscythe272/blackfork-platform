# Agent Plane — Agents as a Service, One Job at a Time

> **In one line:** Every agent job enters through a signed-token door with a quota per caller, runs under its own short-lived identity with its own grant, and leaves a record; the Control Mapper is the first agent to join the Evidence Collector there.

**You are here:** START HERE › Provenance › Agent Plane
**Audience:** 🟡 engineer · **Reads in:** ~6 min

## The 30-second version

Until now the Evidence Collector ran as a one-off process that someone started by
hand. The agent plane turns agents into a service: a caller presents a signed token
naming who they are and asks for one job from one agent. The service checks the token,
checks that this caller has not used up their allowance, mints a fresh token for the
agent's own identity that lasts only as long as the job, runs the job behind the same
guardrails as before, and writes down who asked, which agent ran, how long it took, and
what happened. The caller's identity and the agent's identity are different on
purpose: a caller may ask for a job, but only the agent's identity is granted tools at
the door. The second agent, the Control Mapper, reads a control's requirement and the
evidence held for it and drafts the statement an assessor will read, citing every row
and the control id it read, and saying plainly when there is nothing to cite.

## The picture

```mermaid
flowchart LR
  CALLER["Caller<br><i>signed token, one job request</i>"] --> DOOR["Agent service<br><i>verify caller, apply quota</i>"]
  DOOR --> TOKEN["Job token<br><i>agent's own identity, minutes long</i>"]
  TOKEN --> AGENT["Agent<br><i>collector or mapper, with rails</i>"]
  AGENT --> GW["Gateway<br><i>policy per identity, audit</i>"]
  GW --> RECORD["Job record<br><i>who, which, how long, outcome</i>"]
```

## How it works

1. **Caller.** Anything that wants a job done: the eval runner, a person's script, later
   the Report Writer asking the mapper for statements. It carries a token for its own
   identity, signed with the key the gateway trusts.
2. **Agent service.** Verifies the caller's token, refuses a bad or missing one, and
   applies the caller's quota: thirty jobs an hour by default, a bucket per caller, so
   one caller's flood cannot exhaust another's allowance. A refused request is recorded
   like any other.
3. **Job token.** For an accepted job the service mints a token for the agent's own
   identity, valid for fifteen minutes. The caller never holds it.
4. **Agent.** The Evidence Collector takes a question; the Control Mapper takes a system
   and a control. Both run behind the input and output guardrails, with the same
   toolkit workflow and a prompt written for their job.
5. **Gateway.** Every tool call carries the job token, so policy decides per agent
   identity and the audit trail names the agent, not the caller. The mapper's grant is
   narrower than the collector's: it reads evidence and controls, and cannot fetch a
   single row by id or search the catalog.
6. **Job record.** One line per job: who asked, which agent, a hash of the input rather
   than the input, whether a rail blocked it, how long it took, and the outcome.

## The details

**The Control Mapper.** Its prompt tells it to read the control's requirement first,
then the evidence, then write two to four sentences on how the requirement is met,
citing the row id of every piece of evidence it relies on and the control id it read.
If the evidence call returns nothing, it says no evidence is held and cites nothing.
Two eval cases hold it to that: one control with evidence, where the statement must
cite the two rows and the control; one control with none, where the answer must say so
and no row id may appear.

**The quota, and why it lives here.** The threat model's caller-quota row waited
through two phases because a one-question-per-process agent has nowhere to keep a
count. A service does. The quota is the same token-bucket the gateway uses for its
per-identity limit, keyed by caller.

**What the record holds and what it does not.** The record holds a hash of the input,
never the input: questions can carry the very text the redaction rules keep out of
storage. The durable, chained record of what an agent actually did is the gateway's
audit trail; the job record is the index to it.

**Where it runs.** On Compose, `agent-service` on the edge network with the gateway and
the trace collector, port 8080, jobs recorded under `jobs/`. On Cloud Run, `agents-dev`
at scale to zero, open on the network because it checks its own tokens, with the
signing key and the model key from Secret Manager and one instance holding the quota
buckets. The eval runner can post its cases to either with `--via-service`.

**The Risk Analyst, isolated.** The third job type, the assessor, is the investigation
workflow: the service reads the requirement and the evidence through the gateway as
the mapper, has the mapper draft its statement, assembles the finding, and sends it to
the Risk Analyst. The analyst is a separate service with its own signing key, reached
over the agent-to-agent protocol's shape (an agent card and `message/send`), holding
no identity at the gateway, no gateway address, no bucket, and on Compose no route to
any of them; in the cloud only the agent service's identity may invoke it, and it
checks its own token on top. Its score is deterministic, computed from facts about the
evidence: how many rows, how many sources, how fresh, whether the statement cites rows
that exist. Text is input to the explanation only, so an instruction planted in a
statement cannot move the number, and a test proves it. The explanation is written
afterwards by the model and checked to still name the severity and score it was given
(ADR-004). Evals: both workflow cases pass locally, in process and through the service: the evidence case rated low with both rows cited from two corroborating sources, the no-evidence case rated high.

**The Report Writer, and the signature no agent can give.** The fourth job type
drafts a packet for one system: for each control it runs the assessor, then assembles
the mapper's statements and the analyst's verdicts. The writer adds no prose of its
own. A deterministic rule checks every statement against the rows the evidence call
returned: a statement that cites a row that does not exist, or none of the evidence
held, is withheld and counted, so the packet carries its own measure of what it could
not stand behind. The first packet caught the mapper inventing an evidence identifier;
the ledger has the entry. The packet is stored as a draft with a hash. Tokens now carry a role,
`agent`, `caller`, or `person`; every job token is an agent's, and only a person's own
tooling mints `person`. The signing route refuses any other role and records the
refusal; the packet store checks the role again; the signature binds who, when, and
the hash of exactly what was signed; and export is refused unless the packet is
signed and unchanged since (ADR-007). In the cloud, the first assessor and packet jobs after the merge failed at the
analyst hop: the agent image lacked the library that mints the identity token the
analyst's door requires, a path no laptop run exercises (ledger entry 20); the image
now carries it. Evals: through the service the packet case passes with both statements kept, the sensor's alert row ev-0004 and the audit-log row ev-0003 cited, the no-evidence control rated high, and the packet then signed by a person and exported; an in-process run the same evening recorded one control whose mapping failed on an empty model completion, and the packet reported the failure instead of scoring it, which the eval counts as a fail as designed. The done-when for this step,
one sensor row becoming a cited line in a draft packet with a person's approval step
in the loop, is met: the sensor's alert row is cited in the packet's audit-logging
statement, and the packet cannot leave until a person signs it.

**What is not here yet.** Token spend per job, which the runner does not yet surface;
the workload profile measured it through a proxy instead. Packets as documents for an
assessor, a system security plan draft rather than a list of statements, come with the
assurance plane's re-scoring in step 4.

## Why it's built this way

Agents that a person starts by hand cannot be quota'd, audited per caller, or composed
into a workflow; a service can (BR-3). Separating the caller's identity from the
agent's keeps the policy about agents and the accountability about callers, and a
job-long token means a leaked one is worth minutes (BR-7, BR-8). The mapper exists
because a packet needs statements that cite what they rest on, and an agent that
reads the control text and the evidence before writing produces exactly that (BR-2).

## Go deeper

- `context-plane.md` — the door every job's tool calls go through
- `v1-slice.md` — the Evidence Collector and the guardrails both agents share
- `../02-architecture/agent-threat-model.md` — B1 rows for the caller door and the quota
