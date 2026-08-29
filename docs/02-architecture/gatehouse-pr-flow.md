# Gatehouse PR Flow

> **In one line:** A pull request's path through the deterministic lane, the LLM judge, and (only when flagged) a human.

**You are here:** START HERE › Architecture › Gatehouse PR Flow
**Audience:** 🟡 engineer · **Reads in:** ~2 min

> **v1 diagram** — scheduled for a linear-readability rework (see roadmap). The
> step-numbering system is described in the diagram's own legend.

## The 30-second version

A pull request meets exact rules first — missing threat model or a codified requirement violation blocks the merge in minutes with the rule cited — then an LLM judge scores design quality against a versioned rubric, and only flagged changes pull in a human. Time flows top to bottom; every arrow is numbered.

## The picture

```mermaid
sequenceDiagram
    autonumber
    actor Dev as Developer
    participant GH as GitHub PR
    participant Det as Lane 1 · Deterministic checks (blocking)
    participant Judge as Lane 2 · AppSec judge agent (NAT + NIM)
    participant Sec as Human AppSec (flagged PRs only)

    Note over Dev,Sec: HOW TO READ: time flows top to bottom, and every arrow is<br>auto-numbered in the order it happens. An "alt" box is a fork —<br>only ONE of its branches happens for any given PR.

    Dev->>GH: Open PR (code + docs in one change)
    GH->>Det: Required status checks fire

    Note over Det: First the cheap, exact rules.<br>Presence: did src/ change without updating the<br>architecture diagram or threat model? (BR-4)<br>Policy-as-code (Rego): password min length ≥ 15 per<br>NIST 800-63B r4, no secrets in config, TLS pinned.

    alt any deterministic rule fails
        Det-->>GH: BLOCK merge — cite the exact rule + standard
        GH-->>Dev: Fix and push (feedback in ~2 minutes)
    else all rules pass
        Det-->>GH: Status check green
        GH->>Judge: Send diff + diagram + threat model
        Note over Judge: Now the judgment call no regex can make.<br>Rubric scoring: STRIDE coverage, trust boundaries<br>drawn, data flows labeled, auth design addressed.
        Judge-->>GH: Structured review comment + rubric score (BR-3)
        alt judge flags high risk
            GH->>Sec: Request human review
            Sec-->>GH: Approve or request changes
        else standard change
            Note over GH: No human needed — the 30-minute SLA holds
        end
        GH-->>Dev: Merge when green
    end

    Note over Det,Judge: Every decision lands in the audit table (BR-7).<br>The judge is graded against a planted-flaw eval set —<br>advisory first, promoted to blocking once its precision earns it.
```

## Why it's built this way

Deterministic-before-probabilistic is the gate's core principle (BR-3, BR-4): never ask a model to do a parser's job, and give the judge blocking power only after its precision is measured. This sequence shows exactly where each kind of check sits.
