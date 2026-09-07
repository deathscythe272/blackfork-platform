# Architecture Decision Records

Numbered, immutable decisions with reasoning. Planned set (from the architecture
narrative's "where the whys become ADRs" map):

| ADR | Decision | Serves |
|---|---|---|
| [001](ADR-001-mcp-auth-gateway.md) | Custom auth/audit gateway in front of the MCP server — **accepted** | BR-7, BR-8 |
| 002 | Iceberg lakehouse (bronze/silver/gold) over proprietary warehouse | BR-2, C4 |
| [003](ADR-003-mcp-only-parameterized-tools.md) | MCP as the sole data path; parameterized tools, no model-written SQL — **accepted** | BR-7, BR-8 |
| 004 | Four narrow agents; Risk Analyst isolated behind A2A | BR-3 |
| 005 | Gatehouse two lanes; advisory→blocking promotion by measured precision (incl. fail-open/closed) | BR-3, BR-4, BR-9 |
| 006 | Redaction before storage — data minimization as primary PII control | BR-7, C2 |
| 007 | Human sign-off required on all outbound packets | C3, BR-7 |
| 008 | Hosted NIM for dev; self-hosted NIM containers as the CUI path | C2, C4 |
