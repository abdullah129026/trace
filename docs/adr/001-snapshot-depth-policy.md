# ADR-001: Snapshot depth policy

Date: 2026-10-22
Status: accepted

## Context

The tracer snapshots every local variable at every step. Unbounded snapshots
would explode trace payloads on loopy code (a list growing to 10k items,
snapshotted 2,000 times).

## Decision

- Primitives (None, bool, int, finite float, short str) pass through as-is.
- Containers become a summary: type name, length, and a shallow preview of
  the first 5 items. Anything past that is cut.
- Nesting deeper than 3 levels becomes a truncation marker naming the type.
- Every cut carries `"__trace_truncated__": true` and names its type.
  Nothing is dropped silently.
- Long strings and big reprs are cut at 2,000 chars with the same marker.

## Alternatives considered

- Full deep copy: honest but unbounded; a 1,000-step trace of growing
  structures would be megabytes and kill scrubbing.
- repr-only: bounded, but the variables panel needs structure (length,
  preview) to be useful, not a flat string.

## Consequences

The variables panel must render truncation markers as UI ("list, 10,000
items, showing 5"), never as missing data. Caps live in `app/config.py`
so tuning is one edit.
