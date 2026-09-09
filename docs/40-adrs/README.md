# Architecture Decision Records

Numbered, immutable decisions with reasoning. Planned set (from the architecture
narrative's "where the whys become ADRs" map):

| ADR | Decision | Serves |
|---|---|---|
| [001](ADR-001-mcp-auth-gateway.md) | Custom auth/audit gateway in front of the MCP server — **accepted** | BR-7, BR-8 |
| [002](ADR-002-iceberg-lakehouse.md) | Iceberg lakehouse (bronze/silver/gold) over proprietary warehouse; readers open tables from a pointer, no catalog — **accepted** | BR-2, C4 |
| [003](ADR-003-mcp-only-parameterized-tools.md) | MCP as the sole data path; parameterized tools, no model-written SQL — **accepted** | BR-7, BR-8 |
| [004](ADR-004-narrow-agents-risk-analyst-isolated.md) | Narrow agents, one identity and grant each; the Risk Analyst isolated behind its own key over A2A, no grant at the door, deterministic score — **accepted** | BR-3, BR-8 |
| [005](ADR-005-two-lanes-promotion-by-precision.md) | Gatehouse two lanes; advisory→blocking promotion by measured precision (incl. fail-open/closed) — **accepted** | BR-3, BR-4, BR-9 |
| [006](ADR-006-redaction-before-storage.md) | Redaction before storage — data minimization as primary PII control; a check that does not trust the redactor — **accepted** | BR-7, C2 |
| [007](ADR-007-human-signoff-on-outbound-packets.md) | A person signs every packet that leaves and no agent can: role claims, a hash-bound signature, export refused unsigned — **accepted** | C3, BR-7 |
| 008 | Hosted NIM for dev; self-hosted NIM containers as the CUI path | C2, C4 |
