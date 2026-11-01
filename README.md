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

## Deploy

Order matters: the frontend bakes `NEXT_PUBLIC_API_URL` in at build
time, so bring the backend up first, then deploy the frontend.

Backend (Render, free tier):

1. Dashboard: New > Blueprint, pick this repo. `render.yaml` builds
   `backend/Dockerfile`, which includes the Node runtime the JavaScript
   sandbox needs. Health check is `/health`.
2. Set `GROQ_API_KEY` in the service's dashboard settings. Until it is
   set, the co-pilot answers 503 and everything else still works.
   `GROQ_MODEL` is optional (defaults to llama-3.3-70b-versatile).
3. Note the service URL, e.g. `https://trace-api.onrender.com`.

Frontend (Vercel):

1. Import this repo, set the root directory to `frontend`.
2. Set `NEXT_PUBLIC_API_URL` to the Render backend URL from above,
   then deploy. Changing it later needs a redeploy, since Next.js bakes
   public env vars in at build time.
3. No `vercel.json` needed; the Next.js defaults cover it.

Local env templates live at `backend/.env.example` and
`frontend/.env.example`. Real values go in dashboards and local `.env`
files only, never in the repo. Render free tier sleeps after
inactivity; the landing page already warns first visitors about the
wake-up wait.

## Scope (v1)

Rooms by shareable code, no accounts. Python and JavaScript tracing, sync code only. Traces are recorded, then scrubbed; no breakpoints or live step-through. The full binding list lives in `~/workspace/user/files/trace-build-prompt.md`, the sole source of truth for this build.

## Status

Day 6 of a 7-day build: deploy configs, rate limits, and the security
checklist pass are in. Day 7 (2026-11-02) is dogfooding and ship.
