# Trace security checklist, Day 6 pass (2026-11-01)

Pre-deploy gate from the build prompt's risk register. Each item was
checked against the code as pushed on Day 6, not assumed from earlier days.
Findings fixed the same day are marked FIXED; the rest are accepted v1
trade-offs, named so nobody is surprised by them later.

## Checked and clear

- User code runs only in the sandbox subprocess (scrubbed env, no HOME,
  no secrets, read-only temp workdir, rlimits, wall timeout, step cap).
  Never in the API process. `backend/app/sandbox.py`.
- Python imports restricted to the allowlist in `config.py`, plus the
  audit hook in `sandbox_driver.py` as a second layer. JS runs in a `vm`
  context with no require, process, fs, or network. `js_driver/tracer.js`.
- Every API input validated server-side with Pydantic: source non-empty
  and under the byte cap, language allowlisted, room code matched against
  the 6-char alphabet, question capped, step index bounds-checked.
- Trace values are untrusted data and render as text only. No
  `dangerouslySetInnerHTML` or `innerHTML` anywhere in the frontend.
- No secret, token, or key anywhere in the repo, in logs, or in the
  browser bundle. The Groq key comes from the `GROQ_API_KEY` env var
  only; the only `NEXT_PUBLIC_` variable is the API base URL.
- Logs carry counts and ids only (language, room, step, status). Never
  user code, questions, or explanations.
- Rate limits per IP on `/execute` (20/min), room creation (30/min),
  and the co-pilot (20/min), each in its own bucket, verified live on
  Day 6 against the production-mode server.
- Trace ids are random uuid4 hex; room membership is by code by design.
  No accounts in v1, so there is no session or password surface.
- Dependencies pinned: Python exact pins in `requirements.txt`,
  frontend and JS driver `package-lock.json` committed, no unpinned
  ranges. `npm audit` could not run on Day 6 (the registry audit
  endpoint is unreachable from this build VM), so no audit result is
  claimed; the Day 2 OSV check on the JS driver's acorn pin (0 vulns)
  still stands, and a registry audit should run in CI before launch
  day if the endpoint is reachable there.
- `X-Content-Type-Options: nosniff` on API responses.

## FIXED on Day 6

- Driver stderr leaked into the sandbox error, which the API logged.
  A driver crash traceback can quote user source lines, so the error now
  carries only the exit code. Guarded by
  `test_driver_crash_error_never_carries_driver_stderr`.

## Accepted v1 trade-offs (deliberate, revisit at 10x)

- CORS is a wildcard: the API is public by design (rooms by code, no
  accounts, no credentials), so there is nothing credentialed to steal.
- Rooms and traces live in memory on one instance; rate limits are
  per-process. A second instance would need sticky sessions or the
  Redis hook from the prompt.
- Room codes are 6 chars from a 32-char alphabet: guessable with
  sustained probing, but rooms hold no private data and the code is the
  only sharing mechanism in v1. Rate limits blunt bulk probing.
- CI actions are pinned to major versions (`@v4`/`@v5`), not full SHAs.
  Workflow permissions are minimal (`contents: read`).
- Render free tier sleeps after inactivity; the landing page already
  tells first visitors the first run can take half a minute.
