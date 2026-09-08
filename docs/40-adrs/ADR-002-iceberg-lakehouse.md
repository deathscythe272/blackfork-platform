# ADR-002 — Iceberg tables in a bucket, three layers, readable without a catalog

**Status:** accepted
**Serves:** BR-2, C4
**Date:** 2026-09-08

## Context

Provenance stores evidence for months and serves it to agents through fixed queries.
The store has to keep what arrived, hold a redacted copy for reading, and expose a
narrow view, and it has to cost nearly nothing while nobody is running a demo (C4). A
managed warehouse does the job and bills for it whether or not anyone is asking. The
platform already has a bucket per environment and an identity model built on who may
read which bucket.

## Decision

Three layers, bronze, silver, and gold, each an Apache Iceberg table stored as files in
the environment's lakehouse bucket, or in a folder on a laptop with the same code.
Iceberg gives each table a schema, snapshots, and a single metadata file that describes
its current state. The pipeline writes through a small SQLite catalog so it can find
tables by name. Readers do not use the catalog: every table publishes a pointer to its
current metadata file beside itself, and a reader loads the table from that file with
nothing more than the right to read the bucket. Gold is partitioned by `system_id`.
Queries run in DuckDB over the files.

## Consequences (including what we gave up)

- Idle cost is storage only: kilobytes today, cents at any realistic size.
- A reader needs no service to be up, and no credential beyond bucket read, which is
  exactly the identity model the context plane already enforces.
- Bronze is never rewritten, so a dispute about what a source said is settled by
  reading it.
- Given up: a shared catalog service that many writers could coordinate through. One
  pipeline writes today; if a second writer arrives, the catalog becomes a REST
  service and the pointer stays.
- Given up: a warehouse's query planner and concurrency. The evidence server runs
  fixed queries over small, partitioned tables; the day that is too slow, the answer
  is a bigger DuckDB, not a warehouse.

## Alternatives considered

- **BigQuery or another managed warehouse.** Simplest to query, and the platform
  would carry a bill and a second identity model for the one thing it stores.
- **Plain Parquet files with no table format.** Cheaper still, and no schema
  evolution, no snapshots, no way to say which files are the current table.
- **DuckDB files as the store.** What the slice does today for thirteen rows. A single
  file cannot be written by a pipeline and read by a service at once without copying
  it, and it has no history.
