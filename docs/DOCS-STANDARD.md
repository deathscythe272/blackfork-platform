# Documentation Standard

> **In one line:** Every document in this repo follows one template, so you learn to read
> our docs once and can then navigate any of them in seconds.

**You are here:** START HERE › Docs Standard
**Audience:** 🟢 anyone · **Reads in:** ~3 min

## The 30-second version

These docs are built to be screenshared with a mixed room. Every doc opens with the same
orientation block — what it is, who it's for, a 30-second summary — then one simple
left-to-right diagram, then technical depth, then the reasoning. If you know this
pattern, you know every document here.

## The template

Every doc contains these sections, in this order:

```
# Title
> In one line: <what this doc covers, one sentence>
You are here: <breadcrumb>        Audience: 🟢/🟡/🔴        Reads in: ~X min

## The 30-second version     ← plain English, no acronyms, anyone in the room can follow
## The picture               ← ONE linear diagram (rules below)
## How it works              ← numbered walkthrough matching the diagram step-for-step
## The details               ← full technical depth (🔴 material lives here)
## Why it's built this way   ← rationale, citing BR-x requirements and ADR-x decisions
## Go deeper                 ← links to sub-docs
```

## Audience levels

| Badge | Who it's for | What they get |
|---|---|---|
| 🟢 | Anyone — recruiter, hiring manager, PM | The 30-second version and the picture are enough |
| 🟡 | Engineers | Add "How it works" — the numbered walkthrough |
| 🔴 | Deep-dive reviewers | Add "The details" — schemas, configs, edge cases |

A doc's badge marks the *deepest* level it serves. Every doc serves 🟢 at the top
regardless — that's the point.

## Diagram rules

These exist because dense diagrams don't read; linear ones do.

1. **Left-to-right only** (`flowchart LR`), one primary path. Time-ordered workflows may
   use sequence diagrams instead.
2. **Seven nodes maximum.** If the flow needs more, split it into "Part 1" and "Part 2"
   diagrams shown in sequence — never cram.
3. **Every node = a name plus a gloss of six words or fewer.** No unexplained boxes.
4. **Forks are fine; crossings are not.** Arrows may branch, never weave back over the
   flow.
5. **Diagram and walkthrough match one-to-one.** The numbered list under "How it works"
   follows the boxes in order, left to right.
6. In the repo, diagrams live inside markdown as ` ```mermaid ` fences so GitHub renders
   them inline.

## Writing rules

- The 30-second version is mandatory and acronym-free.
- Define every acronym on first use *in each doc* — readers land on pages cold.
- "Why it's built this way" must cite at least one business requirement (BR-x) or
  architecture decision (ADR-x). Rationale without a source is opinion.
- State the honest read time. A "5-minute doc" that takes twenty breaks trust.

## Why it's built this way

Interview screenshares put five people with five backgrounds on one page with no warning.
A consistent orientation block means nobody is lost for more than ten seconds, and depth
is always one scroll away instead of in the way (serves BR-3's spirit: decision velocity —
here, for readers). The template is also itself an exhibit: documentation standards are
how engineering teams scale understanding, which is the mentoring half of this portfolio.
