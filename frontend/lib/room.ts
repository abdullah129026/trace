/** Shared room constants, API helpers, and small utilities. */

import type { FullTrace } from "./trace";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const ROOM_CODE_RE = /^[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{6}$/;

export type Language = "python" | "javascript";
export const LANGUAGES: Language[] = ["python", "javascript"];

export interface RoomInfo {
  code: string;
  members: number;
  last_trace_id: string | null;
}

export interface TraceSummary {
  language: string;
  status: "ok" | "error" | "truncated";
  steps_captured: number;
  truncated: boolean;
}

export interface TracePayload {
  trace_id: string;
  summary: TraceSummary;
}

/** Cursor colors for remote collaborators. Solid hues, no gradients. */
export const CURSOR_COLORS = [
  "#047857", // emerald (matches the accent)
  "#b45309", // amber
  "#0284c7", // sky
  "#be123c", // rose
  "#7c3aed", // violet
  "#4d7c0f", // lime
  "#c2410c", // orange
  "#0e7490", // cyan
];

const NAME_ADJECTIVES = [
  "amber", "blue", "brisk", "calm", "clever", "dapper", "eager", "fuzzy",
  "hasty", "jolly", "keen", "lively", "nimble", "patient", "quiet", "rapid",
  "silly", "swift", "tidy", "witty",
];
const NAME_ANIMALS = [
  "fox", "wren", "otter", "badger", "heron", "mole", "newt", "owl",
  "panda", "quail", "raven", "stoat", "toad", "vole", "wombat", "yak",
];

const NAME_KEY = "trace.displayName";

/** A stable, human display name per browser. No accounts in v1. */
export function getDisplayName(): string {
  if (typeof window === "undefined") return "guest";
  let name = window.localStorage.getItem(NAME_KEY);
  if (!name) {
    const pick = (xs: string[]) => xs[Math.floor(Math.random() * xs.length)];
    name = `${pick(NAME_ADJECTIVES)}-${pick(NAME_ANIMALS)}`;
    window.localStorage.setItem(NAME_KEY, name);
  }
  return name;
}

/** Turn an http(s) API base into the ws(s) base for sockets. */
export function wsBase(): string {
  return API_BASE.replace(/^http/, "ws");
}

export async function createRoom(): Promise<string> {
  const res = await fetch(`${API_BASE}/rooms`, { method: "POST" });
  const body = await res.json();
  if (!res.ok) throw new Error(body?.error?.message ?? "Could not create a room.");
  return body.code as string;
}

export async function fetchRoom(code: string): Promise<RoomInfo> {
  const res = await fetch(`${API_BASE}/rooms/${code}`);
  const body = await res.json();
  if (!res.ok) throw new Error(body?.error?.message ?? "Could not load the room.");
  return body as RoomInfo;
}

export async function fetchTrace(traceId: string): Promise<FullTrace> {
  const res = await fetch(`${API_BASE}/traces/${traceId}`);
  const body = await res.json();
  if (!res.ok) throw new Error(body?.error?.message ?? "Could not load the trace.");
  return body as FullTrace;
}

export interface CopilotAnswer {
  trace_id: string;
  step_index: number;
  line: number;
  explanation: string;
}

async function copilotQuery(
  path: string,
  traceId: string,
  stepIndex: number,
  question?: string,
): Promise<CopilotAnswer> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(
      question === undefined
        ? { trace_id: traceId, step_index: stepIndex }
        : { trace_id: traceId, step_index: stepIndex, question },
    ),
  });
  const body = await res.json();
  if (!res.ok) throw new Error(body?.error?.message ?? "The co-pilot could not answer.");
  return body as CopilotAnswer;
}

/** Explain one step of a stored trace, using only that trace. */
export function explainStep(traceId: string, stepIndex: number): Promise<CopilotAnswer> {
  return copilotQuery("/explain", traceId, stepIndex);
}

/** Ask a question about one step of a stored trace. */
export function askTrace(
  traceId: string,
  stepIndex: number,
  question: string,
): Promise<CopilotAnswer> {
  return copilotQuery("/ask", traceId, stepIndex, question);
}

export function inviteLink(code: string): string {
  return `${window.location.origin}/r/${code}`;
}
