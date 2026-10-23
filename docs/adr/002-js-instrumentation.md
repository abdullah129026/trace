# ADR-002: JavaScript instrumentation approach

Date: 2026-10-23
Status: accepted

## Context

The JS tracer must produce the same schema-v1 trace as the Python tracer
(line, stack, locals, stdout per step) from arbitrary user snippets, inside
the sandbox. Python uses `sys.settrace`; JS has no equivalent, so we
rewrite the source before running it.

## Decision

- Parse with acorn (pinned 8.19.0, 0 known vulns per OSV on 2026-10-23).
- Two passes over the ESTree AST:
  1. Scope pass: collect declared names per function scope (params,
     var/let/const, function/class names, catch params). Also the v1
     capability gates: async/yield and import/export are clean error
     traces, not hangs.
  2. Instrumentation pass: splice `__step__(line, [[name, () => name], ...])`
     before every statement. Locals are captured through getter thunks so
     TDZ/out-of-scope names are skipped instead of throwing. Unbraced
     single-statement bodies (`if (x) foo();`) are wrapped in braces first,
     or the step call would steal the body. `for` init declarations are
     not statements and are skipped (the loop carries the steps).
- Loops with empty bodies (`while (true) {}`) or lone semicolons get a
  forced step inside the body; otherwise the step cap could never trip.
- Stack tracking: `__enter__(name)` / `__exit__()` in try/finally around
  every function body (arrow expression bodies are rewritten to block
  form). Stack frames past the cap get one explicit truncation marker.
- A final `__step__(lastLine, [...], "return")` is appended, mirroring the
  Python tracer's module-return step and capturing the finished state.
- Run in `vm` with a minimal global surface: no require, process, Buffer,
  timers, or fetch. `console.log` is captured to the stdout buffer.
- Step-limit enforcement: the step function throws a unique sentinel past
  the cap. The sentinel cannot be permanently swallowed: the driver's
  appended final step sits outside any user try/catch, so a caught sentinel
  always rethrows there and the run still ends `truncated` (verified by
  probe). The vm timeout (80% of the wall budget) and the parent's wall
  timeout are the backstops.

## Alternatives considered

- Regex/source-rewriting without a parser: fragile on real JS, rejected.
- Running the tracer in-process in the API: violates the sandbox rule,
  rejected outright.
- Exposing full Node globals and blocking selectively: denylists rot;
  the minimal-globals allowlist is smaller to audit.

## Consequences

- The instrumented code is throwaway per run; helper names are random per
  run and collision-checked against declared names.
- Snapshot policy mirrors ADR-001 (`array`/`object` summaries, same
  truncation marker key).
- Known ceiling: like the Python sandbox, this targets casual abuse, not
  a determined attacker (vm escapes, prototype gadgets). Documented, not
  fixed, for v1.
