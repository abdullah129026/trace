# Trace

Real-Time Collaborative Code Execution Visualizer. "Like Figma, but for debugging."

**Live app:** https://trace-swwy.vercel.app
**API:** https://trace-api-0k5u.onrender.com

## What Trace is

Debugging is a team activity that we still do alone. Python Tutor is single user and Python only. Debugging over a call means one person shares a screen while everyone else watches, and nobody can point at the exact line where a variable went wrong.

Trace makes the run itself the shared artifact. Paste a snippet, invite someone with a room code, and watch the code run together. Everyone sees the same execution, scrubs back and forth through it, inspects variables and the call stack at every step, and asks the AI co-pilot why it broke.

## How it works

1. **Create or join a room.** A room is a 6 character code, no accounts, no sign-up. Share the code and the other person is in.
2. **Edit together.** Everyone in the room edits the same code live, with visible remote cursors (Yjs CRDT over WebSockets), the way a shared doc works.
3. **Run.** Anyone hits Run. The code executes once in a sandbox (see below) and the run is recorded as a trace: every step, with the line, the variables, the stack, and stdout.
4. **Scrub the execution.** The trace is a recording, not a live step-through. Drag the timeline scrubber or press play (with speed controls) and the variables and stack panels update step by step. An execution graph shows the path the run took.
5. **Ask the co-pilot.** Select a step and ask why it broke. The co-pilot explains using only the values present in the trace, and it has to cite the step index and line it is talking about.

## Under the hood

**Tracing.** Python is traced with `sys.settrace`. JavaScript is instrumented at statement boundaries and run in a Node `vm` context. Both tracers emit one versioned trace schema, so the frontend never cares which language produced the steps.

**Sandbox.** User code never runs in the API process. Each run spawns a capped subprocess with a scrubbed environment, no network, a read only workdir, CPU and memory caps, a wall timeout, and a step cap. The JavaScript context gets no `require`, no filesystem, no network.

**Co-pilot boundary.** The co-pilot only knows what the trace contains. If no Groq key is configured it answers 503 and everything else keeps working; the panel says so plainly instead of inventing an answer. A wrong explanation in a debugger costs more than no explanation.

## What v1 does and does not do

In v1: rooms by shareable code, Python and JavaScript tracing (sync code only), live collaborative editing with presence, recorded traces with scrubbing, and the co-pilot.

Deliberately not in v1: accounts, saved rooms, breakpoints or live step-through, a third language, a public gallery. Rooms and traces live in memory on one backend instance. These are named trade-offs, not oversights.

## Layout

- `backend/`: FastAPI service with the execution API, Python tracer, JS tracer (Node subprocess), and Yjs collaboration relay.
- `frontend/`: Next.js (App Router) + TypeScript + Tailwind room UI, execution graph, timeline scrubber, co-pilot panel.
- `docs/adr/`: architecture decision records.

## Quickstart (dev, verified 2026-11-02)

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

Order matters: the frontend bakes `NEXT_PUBLIC_API_URL` in at build time, so bring the backend up first, then deploy the frontend.

Backend (Render, free tier):

1. Dashboard: New > Blueprint, pick this repo. `render.yaml` builds `backend/Dockerfile`, which includes the Node runtime the JavaScript sandbox needs. Health check is `/health`.
2. Set `GROQ_API_KEY` in the service's dashboard settings. Until it is set, the co-pilot answers 503 and everything else still works. `GROQ_MODEL` is optional (defaults to llama-3.3-70b-versatile).
3. Note the service URL, e.g. `https://trace-api.onrender.com`.

Frontend (Vercel):

1. Import this repo, set the root directory to `frontend`.
2. Set `NEXT_PUBLIC_API_URL` to the Render backend URL from above, then deploy. Changing it later needs a redeploy, since Next.js bakes public env vars in at build time.
3. No `vercel.json` needed; the Next.js defaults cover it.

Local env templates live at `backend/.env.example` and `frontend/.env.example`. Real values go in dashboards and local `.env` files only, never in the repo.

Render free tier sleeps after inactivity, so the first visit can take half a minute to wake up. The landing page warns first visitors about the wait, and the frontend rides out the wake-up page instead of failing.

## Status

Shipped 2026-11-02: three buggy snippets debugged through the finished product (a function returning `None`, list aliasing, the same `None` bug in JavaScript), a 60 iteration loop traced to 124 steps, a two-browser room verified end to end (collab edit, presence, shared run, zero console errors), 91/91 backend tests green, frontend production build green. Full story in `CASE_STUDY.md`, launch drafts in `docs/launch-notes.md`.

One check is still open and is not claimed as done: two real people debugging together in a live room. The two-browser room passed locally in production mode; the live version of that test is the next step.
