# Trace

Real-Time Collaborative Code Execution Visualizer. "Like Figma, but for debugging."

Paste a snippet, invite someone with a room code, and watch the code run together. Scrub back and forth through the execution, see variables and the stack at every step, and ask the AI co-pilot why it broke.

## Layout

- `backend/` — FastAPI service: execution API, Python tracer, JS tracer (Node subprocess), Yjs collaboration relay.
- `frontend/` — Next.js (App Router) + TypeScript + Tailwind: room UI, execution graph, timeline scrubber, co-pilot panel.
- `docs/adr/` — architecture decision records, 3-6 max.

## Quickstart (dev)

Backend:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Stack

Next.js + TypeScript frontend, FastAPI backend, Yjs over WebSockets for collaboration, Groq for the AI co-pilot. Free tiers only: Vercel frontend, Render backend.

## Scope (v1)

Rooms by shareable code, no accounts. Python and JavaScript tracing, sync code only. Traces are recorded, then scrubbed; no breakpoints or live step-through. The full binding list lives in `~/workspace/user/files/trace-build-prompt.md`, the sole source of truth for this build.

## Status

Day 1 of a 7-day build (2026-10-22 to 2026-10-28).
