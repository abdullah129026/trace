# Trace: case study

## The problem

Debugging is a team activity that we still do alone. Python Tutor is
single user and Python only. Debugging over a call means one person shares
a screen while everyone else watches, and nobody can point at the exact
line where a variable went wrong. Trace makes the run itself the shared
artifact: a room of people watch the same execution, scrub through it,
and ask why it broke.

## What I built

A room you join with a 6 character code, no accounts. Everyone edits the
same code live (Yjs CRDT, visible remote cursors), anyone hits Run, and
everyone in the room receives the same trace. The trace is a recording,
not a live step through: an execution graph, a timeline scrubber with
play and speed controls, variables and stack panels, stdout, and an AI
co-pilot that explains a selected step from the trace alone.

User code never runs in the API process. Each run spawns a sandboxed
subprocess with a scrubbed environment, no network, a read only workdir,
CPU and memory caps, a wall timeout, and a step cap. Python tracing uses
`sys.settrace`; JavaScript is instrumented at statement boundaries and
run in a Node `vm` context with no require, fs, or network. Both tracers
feed one versioned trace schema, so the frontend never cares which
language produced the steps.

## Dogfooding, Day 7 (2026-11-02)

I debugged three real buggy snippets through the finished product, plus
a scale check, and ran a two browser room end to end. Every number below
comes from those runs, not from a mock.

**Bug 1: a function that returns None.** A Python `fetch_user` returned
`None` and the caller subscripted the result. The trace is 7 steps. Step
4 is the first step where `user` is `None`, step 5 is the exception
(`TypeError: 'NoneType' object is not subscriptable`). The trace shows
exactly where the value went wrong, one step before the crash, which is
the whole point of the tool.

**Bug 2: list aliasing.** `backup = prices`, then `backup.append(40)`.
Step 3 of the trace shows both `prices` and `backup` at length 4. The
surprise is visible in the variables panel without any explanation
needed.

**Bug 3: the same None bug in JavaScript.** `getUser()` returns null,
`user.name` throws. 4 steps, `user` is null at step 2, the exception
lands at step 3 with the real V8 message. Same panel, same scrubber,
second language.

**Scale check.** A 60 iteration loop produces 124 steps and the correct
total (1770), and the scrubber moves through all of them client side
with no per step server calls.

**Two browsers, one room.** Two separate browser contexts joined the
same room code. Typing in one appeared in the other, presence showed 2
here on both sides, a Run from one browser delivered the finished trace
to both, with zero page or console errors. Screenshots of the landing
page and the room confirmed the layout at desktop and mobile widths.

**One fix the session surfaced.** Function values in the variables
panel showed a Python memory address (`<function fetch_user at
0x...>`), which changes on every run and reads as noise. Snapshots now
render callables as `<function fetch_user>`, covered by a regression
test. Full suite after the fix: 91 of 91 backend tests green, frontend
production build green.

## What the co-pilot can and cannot do

The co-pilot explains a selected step using only values present in the
trace, and it must cite the step index and line. If no Groq key is
configured it answers 503 and everything else keeps working; the panel
says so plainly instead of inventing an answer. That boundary is the
difference between a debugger and a chatbot: a wrong explanation in a
debugger costs more than no explanation.

## What is deliberately not in v1

No accounts, no saved rooms, no breakpoints or live step through, no
third language, no public gallery. Rooms and traces live in memory on
one instance, so a second instance would need sticky sessions or the
Redis hook that is already sketched in the architecture. Render free
tier sleeps after inactivity, so the first visit can take half a minute
to wake up; the landing page says so, and the frontend rides out the
wake up page instead of failing. These are named trade offs, not
oversights, and the v2 list in the launch notes keeps them visible.

## What is still unproven

Two real people in two real browsers have not yet debugged together on
the live deployment. The two browser room passed locally in production
mode and both browsers were real Chromium sessions, but a live room
with two humans is the last check before I call this done. That check
is mine to do next, not something to claim early.

## Stack

Next.js + TypeScript frontend, FastAPI backend, Yjs over WebSockets,
Groq for the co-pilot, Render for the backend, Vercel for the frontend.
Zero budget, free tiers only.

## Links

Live app: https://trace-swwy.vercel.app
API: https://trace-api-0k5u.onrender.com
Repo: https://github.com/abdullah129026/trace
