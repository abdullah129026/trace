# Trace launch notes (drafts, not published)

Publishing is a manual step. These drafts are here so the posts go out
in his voice, with real numbers from the Day 7 dogfood session. Do not
post them from a cron run.

## LinkedIn (short post)

Debugging over a call is broken. One person shares a screen, everyone
else watches, and nobody can point at the exact line where the variable
went wrong.

So I built Trace: paste code, share a room code, and watch the code run
together. Everyone sees the same steps, the same variables, and the same
moment it breaks. Python and JavaScript, no accounts, no setup.

The moment that sold me on it: a function returned None, the caller
trusted it, and the trace showed user turn None one step before the
crash. That is the step you argue about on a call. Now it is just there,
in the panel.

Live: https://trace-swwy.vercel.app
Repo: https://github.com/abdullah129026/trace

Try breaking it. A two person room is where it earns its keep, so grab
a friend and a buggy snippet.

## Dev.to (longer post)

Title: I built a debugger you use with a friend

Body sketch (expand, do not pad):

- The itch: Python Tutor is solo and Python only, and screen share
  debugging means one driver and a row of passengers.
- What Trace does: rooms by code, collaborative editing with visible
  cursors, a sandboxed Python and JavaScript tracer, a scrubbable
  execution graph, variables and stack at every step, and a co-pilot
  that explains a step from the trace alone and cites the step and
  line.
- Three bugs from the dogfood session, with real step numbers: the None
  return (wrong at step 4, crash at step 5), the list aliasing surprise
  (both lists length 4 at step 3), the same None bug in JavaScript
  (null at step 2, exception at step 3).
- The sandbox, briefly: user code runs in a capped subprocess, never in
  the API process, no network, no filesystem, step cap with an honest
  truncation flag.
- What is not in v1: accounts, saved rooms, breakpoints, a third
  language. And the honest caveat: Render free tier sleeps, so the
  first visit takes a while to wake up.
- Close with the ask: open a room with a friend, run something buggy,
  and tell me where the trace lied to you. That is the feedback I can
  actually use.

## v2 parking lot (from the Scope OUT list)

Accounts and saved traces, breakpoints and live step through, Java and
C++ tracers, recorded share links with playback, team workspaces,
constructor args in callable snapshots (Day 7 simplified these to a
name). Nothing here is promised with a date.
