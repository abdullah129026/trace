"""Named execution and tracing limits.

Tuning the product's safety budget is one edit here. Nothing in the tracer
or the API may hardcode its own caps.
"""

SUPPORTED_LANGUAGES = ("python", "javascript")

# Source code size cap on /execute input (bytes).
MAX_SOURCE_BYTES = 100_000

# Hard cap on recorded steps per trace. Exceeding it truncates the trace
# with an explicit flag instead of dropping steps silently.
MAX_TRACE_STEPS = 2_000

# Wall-clock timeout for one execution run (seconds). Enforced by the
# Day 2 subprocess runner; the in-process tracer only knows the step cap.
MAX_WALL_SECONDS = 10

# Per-value repr cap for a single variable snapshot (characters).
MAX_SNAPSHOT_CHARS = 2_000

# How many items of a list/dict get a shallow preview before truncation.
SNAPSHOT_PREVIEW_ITEMS = 5

# Cap on captured stdout per run (characters). stdout_so_far per step is
# derived from this buffer, never logged, never stored beyond the trace.
MAX_STDOUT_CHARS = 50_000

# How many stack frames we keep per step. Deep recursion past this gets an
# explicit marker, not a silent cut.
MAX_STACK_FRAMES = 64

# Traces kept in memory (LRU). Deliberate v1 simplification; the room-store
# interface in rooms.py is the upgrade path to Redis/Postgres.
TRACE_STORE_CAP = 64

# Rooms kept in memory (oldest evicted first). Same v1 simplification.
ROOM_STORE_CAP = 256

# Room code format: 6 chars, unambiguous alphabet (no 0/O, 1/I/l).
ROOM_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
ROOM_CODE_LENGTH = 6

# Sandbox subprocess caps (enforced by app/sandbox.py, never in-process).
# The child gets a scrubbed env, a read-only temp workdir, no network, and
# these rlimits; the wall timeout kills it from the parent.
SANDBOX_CPU_SECONDS = 8
SANDBOX_MEMORY_BYTES = 256 * 1024 * 1024
SANDBOX_FILE_BYTES = 1 * 1024 * 1024

# Node's V8 reserves ~1.5 GB of *virtual* address space just to start, so
# the address-space rlimit has to be generous for javascript runs. The real
# memory bound there is the V8 heap cap passed as --max-old-space-size.
SANDBOX_NODE_MEMORY_BYTES = 2 * 1024 * 1024 * 1024
SANDBOX_NODE_HEAP_MB = 384

# Stdlib modules user code may import inside the sandbox. Everything else
# (os, sys, socket, subprocess, pathlib, ...) raises ImportError. This is
# the list that makes "no network, no filesystem" actually true; the audit
# hook in the sandbox driver is the second layer, not a replacement.
SANDBOX_IMPORT_ALLOWLIST = frozenset(
    {
        "math",
        "random",
        "functools",
        "itertools",
        "collections",
        "re",
        "json",
        "string",
        "statistics",
        "datetime",
        "decimal",
        "fractions",
        "heapq",
        "bisect",
        "operator",
        "copy",
        "unicodedata",
        "numbers",
        "enum",
        "dataclasses",
        "typing",
    }
)

# /execute rate limit: requests per IP per sliding window (seconds).
RATE_LIMIT_EXECUTE_PER_MINUTE = 20
RATE_LIMIT_WINDOW_SECONDS = 60

# /rooms creation rate limit: creations per IP per sliding window (seconds).
RATE_LIMIT_ROOM_CREATE_PER_MINUTE = 30

# Co-pilot (/explain, /ask) rate limit: requests per IP per sliding window.
# The co-pilot costs a model call, so it gets its own bucket, not the
# execution bucket.
RATE_LIMIT_COPILOT_PER_MINUTE = 20

# AI co-pilot: model answer budget (seconds) and question size cap. Past
# the timeout the API answers with a graceful timeout error, not a hang.
COPILOT_TIMEOUT_SECONDS = 5
MAX_QUESTION_CHARS = 1_000
