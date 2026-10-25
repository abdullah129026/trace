/** Pure helpers for the execution visualizer. No React, no DOM, so the
 *  logic can be checked without rendering: step clamping, snapshot
 *  formatting (text only, trace values are untrusted), and graph layout.
 *  The trace is data; the scrubber is an index. */

export interface TraceStep {
  i: number;
  line: number;
  event: "line" | "call" | "return" | "exception";
  stack: string[];
  locals: Record<string, unknown>;
  stdout_so_far: string;
}

export interface FullTrace {
  version: number;
  language: string;
  room_id: string;
  source_lines: string[];
  steps: TraceStep[];
  result: {
    status: "ok" | "error" | "truncated";
    steps_captured: number;
    truncated: boolean;
    error: string | null;
  };
}

export function clampStep(index: number, stepCount: number): number {
  if (stepCount <= 0) return 0;
  if (index < 0) return 0;
  if (index >= stepCount) return stepCount - 1;
  return index;
}

/** Render one snapshot value as plain text. Truncation markers stay
 *  visible and honest; nothing is rendered as HTML anywhere upstream. */
export function formatSnapshot(value: unknown): string {
  if (value === null) return "None";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    return `[${value.map(formatSnapshot).join(", ")}]`;
  }
  if (typeof value === "object") {
    const obj = value as Record<string, unknown>;
    if (obj["__trace_truncated__"] === true) {
      const typeName = typeof obj["type"] === "string" ? obj["type"] : "value";
      const preview = obj["value"];
      const shown = preview === undefined ? "" : `: ${formatSnapshot(preview)}`;
      return `<${typeName} truncated${shown}>`;
    }
    if (typeof obj["type"] === "string" && "length" in obj) {
      // Container summary from the tracer: type, length, shallow preview.
      const preview = obj["preview"];
      const shown = preview === undefined ? "" : ` ${formatSnapshot(preview)}`;
      return `<${obj["type"]} len=${obj["length"]}${shown}>`;
    }
    const entries = Object.entries(obj).map(
      ([k, v]) => `${k}: ${formatSnapshot(v)}`,
    );
    return `{${entries.join(", ")}}`;
  }
  return String(value);
}

/** Lay the execution graph out: x is time (step order), y is the source
 *  line. Loops show up as the path revisiting a row; calls and returns
 *  are just steps like any other, the event label carries the meaning. */
export function graphPoints(
  steps: TraceStep[],
  width: number,
  height: number,
): { x: number; y: number }[] {
  if (steps.length === 0) return [];
  const lines = steps.map((s) => s.line);
  const minLine = Math.min(...lines);
  const maxLine = Math.max(...lines);
  const span = Math.max(maxLine - minLine, 1);
  const padX = 12;
  const padY = 14;
  const innerW = Math.max(width - padX * 2, 1);
  const innerH = Math.max(height - padY * 2, 1);
  return steps.map((s, idx) => ({
    x: padX + (steps.length === 1 ? innerW / 2 : (idx / (steps.length - 1)) * innerW),
    y: padY + ((s.line - minLine) / span) * innerH,
  }));
}

/** Base step length in ms; playback speed divides it. */
export const BASE_STEP_MS = 700;

export function stepIntervalMs(speed: number): number {
  return Math.max(Math.round(BASE_STEP_MS / speed), 50);
}
