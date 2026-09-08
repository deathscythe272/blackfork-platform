# Point the gateway at the shared policy engine

## What

The gateway reads its policy engine address from configuration; this sets the shared
engine's address and the project for the audit topic so local runs match staging.

## Why

One policy engine for every developer instead of one per laptop (ADR-001).

Serves: BR-7
