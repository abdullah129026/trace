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

# Room code format: 6 chars, unambiguous alphabet (no 0/O, 1/I/l).
ROOM_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
ROOM_CODE_LENGTH = 6
