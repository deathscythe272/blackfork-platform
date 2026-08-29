# Context Diagram

> **In one line:** Who's involved and where Provenance and Gatehouse sit — the story is on the numbered arrows, 1 to 8.

**You are here:** START HERE › Architecture › Context Diagram
**Audience:** 🟡 engineer · **Reads in:** ~2 min

> **v1 diagram** — scheduled for a linear-readability rework (see roadmap). The
> step-numbering system is described in the diagram's own legend.

```mermaid
flowchart LR

KEY["HOW TO READ: follow the numbered arrows 1 → 8 —<br>they tell the story in order. The letter A arrows are<br>continuous support, not part of the sequence."]

subgraph BF["BLACKFORK SYSTEMS (fictional) — 180-person defense-adjacent SaaS"]
  ENG["Engineering teams — 60 devs<br><i>ship features weekly; today they wait<br>~6 days for security review</i>"]
  GH["GitHub<br><i>code, pull requests, Actions CI</i>"]
  GHOUSE["GATEHOUSE<br><i>merge-gate agent: blocks PRs missing docs<br>or violating security requirements,<br>reviews design quality</i>"]
  SRC["Cloud + scanners<br><i>GCP audit logs, Trivy/Grype,<br>Security Onion sensor</i>"]
  PROV["PROVENANCE<br><i>evidence lakehouse + GRC agents:<br>continuous, cited audit evidence</i>"]
  SEC["Security team — 3 people<br><i>AppSec lead, GRC analyst, cloud sec —<br>cannot scale by hiring (C1)</i>"]
end

subgraph EXT["OUTSIDE THE COMPANY"]
  PRIME["DoD prime contractor<br><i>the customer whose contract<br>creates the compliance pressure</i>"]
  AUD["External auditor / assessor<br><i>needs current, believable evidence<br>with human sign-off (C3)</i>"]
  NIM["NVIDIA NIM cloud<br><i>hosted LLM inference —<br>free developer tier</i>"]
end

PRIME -.->|"1 · contract flows NIST 800-171 / CMMC<br>requirements down to Blackfork"| SEC
SRC -->|"2 · security telemetry<br>streams in continuously"| PROV
ENG -->|"3 · engineers open PRs"| GH
GH -->|"4 · every PR<br>triggers the gate"| GHOUSE
GHOUSE -->|"5 · verdict + design review<br>back in under 30 min (BR-3, BR-4)"| ENG
GHOUSE -.->|"6 · gate decisions are stored<br>as compliance evidence (BR-7)"| PROV
PROV -->|"7 · draft audit packets, every<br>claim cited (BR-1, BR-2, BR-5)"| SEC
SEC -->|"8 · human-approved<br>evidence"| AUD
GHOUSE -->|"A · LLM calls"| NIM
PROV -->|"A · LLM calls"| NIM

classDef nvidia fill:#76B900,stroke:#4d7a00,color:#111
class NIM nvidia
classDef build fill:#dbeafe,stroke:#1d4ed8,color:#111
class GHOUSE,PROV build
classDef key fill:#f1f5f9,stroke:#64748b,color:#111
class KEY key
```
