# ADR-003: Yjs relay via pycrdt-websocket inside the FastAPI process

Date: 2026-10-24 (Day 3)

## Context

Rooms need a Yjs sync relay for collaborative editing with presence. The
build prompt (0.3) named two candidates: pycrdt-websocket embedded in the
FastAPI process, or a dedicated Node y-websocket sidecar on the same host,
with the Node option pre-approved if the Python library fought the build.

## Spike

Time-boxed spike on Day 3 morning: mounted pycrdt-websocket 0.16.5's
`ASGIServer` (wrapping `WebsocketServer`) as a raw ASGI app inside a test
harness, then connected two real Node clients (yjs 13 + y-websocket 3,
the official JS implementation) to the same room.

Result: text edits synced both ways and awareness states (user names)
appeared on both clients. Re-ran the same two-client script against the
real FastAPI app with the relay mounted at /yjs: identical result.

One spike gotcha, not a library problem: plain `uvicorn` without the
`websockets` package cannot serve WebSocket upgrades at all (500s with
"Unsupported upgrade request"). Fixed by pinning `websockets==17.3`
(OSV: 0 vulns affecting 17.3) alongside `pycrdt-websocket==0.16.5`
(OSV: 0 vulns).

## Decision

Use pycrdt-websocket mounted at /yjs/{code} inside the FastAPI process.
The Node sidecar is dropped.

## Consequences

- Single process, single port. This is what makes the Render free tier
  work: one web service, no inter-process routing, no second port to expose.
- Rooms are keyed by the WebSocket path; the mount admits only
  well-formed codes for rooms created via POST /rooms (4400/4404 close
  otherwise), so there are no orphan relay rooms.
- Empty rooms auto-clean server-side (pycrdt default).
- Risk accepted: pycrdt-websocket is younger than y-websocket. Mitigated by
  the spike proving wire compatibility with the official JS clients for
  exactly the operations v1 needs (text sync, awareness).
- The Day 3 pytest suite covers admission/rejection at /yjs; sync itself is
  covered by the spike script pattern, re-run against the real app.
