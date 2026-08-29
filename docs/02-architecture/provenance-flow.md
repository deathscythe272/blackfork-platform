# Provenance Flow

> **In one line:** One piece of evidence's 14-step journey from raw alert to signed audit packet.

**You are here:** START HERE › Architecture › Provenance Flow
**Audience:** 🟡 engineer · **Reads in:** ~2 min

> **v1 diagram** — scheduled for a linear-readability rework (see roadmap). The
> step-numbering system is described in the diagram's own legend.

```mermaid
flowchart TB

subgraph KEY["HOW TO READ THIS DIAGRAM"]
direction LR
  K1["Follow the numbers 1 → 14: the journey of ONE piece of evidence,<br>from a raw network alert to a signed audit packet.<br>Same number + letters (1a, 1b...) = parallel inputs at that step."]
  K2["Boxes marked ◆ have no step number: they run ALL THE TIME<br>and their text says which steps they support.<br>Layers still match the study guide in the business case, §7."]
end

subgraph L1["LAYER: SOURCES — step 1: five feeds produce raw security facts"]
direction LR
  SO["1a · Security Onion lab<br><i>network sensor VM (Zeek + Suricata) emits alerts —<br>our example follows one of these</i>"]
  GCP["1b · GCP audit logs<br><i>the cloud's record of who did what</i>"]
  SCAN["1c · Trivy + Grype scans<br><i>known CVEs in each container,<br>plus its contents (SBOM)</i>"]
  TF["1d · Terraform state<br><i>what infrastructure is<br>actually deployed</i>"]
  VEX["1e · NVIDIA vuln-analysis blueprint<br><i>agent that judges whether a CVE is<br>truly exploitable here (BR-6)</i>"]
end

subgraph L2["LAYER: PIPELINES — steps 2–6: Dagster cleans and shapes the data"]
direction LR
  ING["2 · Ingest assets<br><i>scheduled jobs land all five<br>feeds as raw records</i>"]
  RED["4 · Presidio redaction<br><i>strips personal data (PII)<br>before long-term storage</i>"]
  QC["6 · Asset checks<br><i>data-quality gate: bad data<br>stops here, loudly</i>"]
  STEW["◆ Pipeline Steward agent<br><i>ON FAILURE ONLY at steps 2–6:<br>diagnoses the broken job, opens a fix PR</i>"]
end

subgraph L3["LAYER: LAKEHOUSE — steps 3, 5, 7: Apache Iceberg tables, queried with DuckDB"]
direction LR
  BRZ["3 · Bronze table<br><i>raw, exactly as received</i>"]
  SLV["5 · Silver table<br><i>cleaned, typed, redacted</i>"]
  GLD["7 · Gold views<br><i>agent-ready: evidence, assets,<br>findings, control status (BR-2)</i>"]
end

subgraph L4["LAYER: MCP ACCESS — steps 8–9: the only door agents may use"]
direction LR
  EMCP["8a · evidence-mcp server<br><i>safe, parameterized queries<br>over Gold views only</i>"]
  CMCP["8b · controls-mcp server<br><i>NIST 800-171 + SOC 2 catalogs in<br>machine-readable OSCAL (BR-5)</i>"]
  GW["9 · Auth gateway — custom build<br><i>verifies identity, asks ◆ OPA to approve,<br>writes ◆ audit log — every call (BR-7)</i>"]
end

subgraph L5["LAYER: AGENTS — steps 10–13: NeMo Agent Toolkit workflows"]
direction LR
  COL["10 · Evidence Collector<br><i>pulls the proof that each<br>control is actually met</i>"]
  MAP["11 · Control Mapper<br><i>links evidence to controls, drafts<br>implementation statements</i>"]
  RSK["12 · Risk Analyst — via A2A<br><i>separate service, own auth;<br>scores and prioritizes</i>"]
  WRT["13 · Report Writer<br><i>assembles the audit packet + SSP<br>draft for human sign-off (BR-1)</i>"]
end

subgraph L6["LAYER: OUTPUT — step 14: what humans receive"]
  PKT["14 · Audit packet + SSP draft<br><i>every claim cites its evidence row;<br>a person approves before anything ships (C3)</i>"]
end

subgraph AO["◆ ALWAYS ON — continuous support, not steps in the journey"]
direction LR
  NIM["◆ NVIDIA NIM endpoints<br><i>hosted LLMs (free dev tier) — the brain<br>steps 10–13 call for every reasoning task</i>"]
  RET["◆ NeMo Retriever + Milvus<br><i>semantic search steps 10–11 use to find<br>related policies, docs, prior evidence</i>"]
  GRD["◆ NeMo Guardrails<br><i>filters the input and output<br>of steps 10–13</i>"]
  OPA["◆ OPA policies (Rego)<br><i>rules-as-code: approves or denies<br>every call made at step 9</i>"]
  AUD["◆ Audit table<br><i>immutable log step 9 writes to —<br>the automation must survive audit too</i>"]
  OT["◆ OpenTelemetry → Grafana<br><i>traces steps 2–13 into dashboards:<br>posture, pipeline health, agent latency/cost</i>"]
  EV["◆ Eval harness<br><i>golden question sets that re-score<br>agents 10–13 after every change</i>"]
  GRK["◆ Garak red-team<br><i>NVIDIA's LLM vulnerability scanner —<br>periodically attacks steps 10–13, publishes findings</i>"]
end

SO --> ING
GCP --> ING
SCAN --> ING
TF --> ING
VEX --> ING
ING --> BRZ
BRZ --> RED
RED --> SLV
SLV --> QC
QC --> GLD
GLD --> EMCP
EMCP --> GW
CMCP --> GW
GW --> COL
COL --> MAP
MAP --> RSK
RSK --> WRT
WRT --> PKT

classDef nvidia fill:#76B900,stroke:#4d7a00,color:#111
class VEX,NIM,RET,GRD,GRK nvidia
classDef custom fill:#dbeafe,stroke:#1d4ed8,color:#111
class GW,STEW custom
classDef gov fill:#fef3c7,stroke:#b45309,color:#111
class OPA,AUD gov
classDef key fill:#f1f5f9,stroke:#64748b,color:#111
class K1,K2 key
```
