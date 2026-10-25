"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import * as Y from "yjs";
import { WebsocketProvider } from "y-websocket";
import {
  API_BASE,
  CURSOR_COLORS,
  Language,
  fetchRoom,
  fetchTrace,
  getDisplayName,
  wsBase,
} from "./room";
import type { FullTrace } from "./trace";

export interface Member {
  clientId: number;
  name: string;
  color: string;
  self: boolean;
}

type Awareness = WebsocketProvider["awareness"];

function collectMembers(aw: Awareness): Member[] {
  const out: Member[] = [];
  aw.getStates().forEach((state, clientId) => {
    const user = (state as { user?: { name?: string; color?: string } } | undefined)?.user;
    if (!user) return;
    out.push({
      clientId,
      name: user.name ?? "Anonymous",
      color: user.color ?? "#64748b",
      self: clientId === aw.clientID,
    });
  });
  out.sort((a, b) => Number(b.self) - Number(a.self) || a.name.localeCompare(b.name));
  return out;
}

/**
 * Owns everything a room page needs: the shared Yjs doc, the editing relay
 * connection, presence, the room event socket (members + finished traces),
 * the shared language, and the run action.
 */
export function useRoom(code: string) {
  const [doc] = useState(() => new Y.Doc());
  const [awareness, setAwareness] = useState<Awareness | null>(null);
  const [yConnected, setYConnected] = useState(false);
  const [eventsConnected, setEventsConnected] = useState(false);
  const [members, setMembers] = useState<Member[]>([]);
  const [memberCount, setMemberCount] = useState(0);
  const [language, setLanguageState] = useState<Language>("python");
  const [roomMissing, setRoomMissing] = useState(false);

  const [runState, setRunState] = useState<"idle" | "running">("idle");
  const [runError, setRunError] = useState<string | null>(null);
  const [trace, setTrace] = useState<FullTrace | null>(null);
  const seenTraceIds = useRef(new Set<string>());

  const loadTrace = useCallback(async (traceId: string) => {
    if (seenTraceIds.current.has(traceId)) return;
    seenTraceIds.current.add(traceId);
    try {
      setTrace(await fetchTrace(traceId));
    } catch {
      // A trace id we cannot load is not worth breaking the room over;
      // the next run replaces it.
    }
  }, []);

  // Editing relay + presence + shared language.
  useEffect(() => {
    const provider = new WebsocketProvider(`${wsBase()}/yjs`, code, doc);
    const name = getDisplayName();
    const color = CURSOR_COLORS[provider.awareness.clientID % CURSOR_COLORS.length];
    provider.awareness.setLocalStateField("user", {
      name,
      color,
      colorLight: `${color}44`,
    });
    setAwareness(provider.awareness);

    const onStatus = ({ status }: { status: string }) => setYConnected(status === "connected");
    const onAwareness = () => setMembers(collectMembers(provider.awareness));
    provider.on("status", onStatus);
    provider.awareness.on("change", onAwareness);
    onAwareness();

    const meta = doc.getMap("meta");
    const applyLanguage = () => {
      const l = meta.get("language");
      if (l === "python" || l === "javascript") setLanguageState(l);
    };
    applyLanguage();
    meta.observe(applyLanguage);

    return () => {
      meta.unobserve(applyLanguage);
      provider.awareness.off("change", onAwareness);
      provider.off("status", onStatus);
      provider.destroy();
      setAwareness(null);
    };
  }, [code, doc]);

  // Room event socket: member counts and finished-trace broadcasts.
  // Reconnects with a flat 2s backoff; the relay provider above reconnects itself.
  useEffect(() => {
    let ws: WebSocket | null = null;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const onMessage = (ev: MessageEvent) => {
      let msg: { type: string; members?: number; last_trace_id?: string | null; trace_id?: string };
      try {
        msg = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (msg.type === "hello") {
        setMemberCount(msg.members ?? 0);
        if (msg.last_trace_id) void loadTrace(msg.last_trace_id);
      } else if (msg.type === "member_joined" || msg.type === "member_left") {
        setMemberCount(msg.members ?? 0);
      } else if (msg.type === "trace" && msg.trace_id) {
        void loadTrace(msg.trace_id);
      }
    };

    const connect = () => {
      if (stopped) return;
      ws = new WebSocket(`${wsBase()}/rooms/${code}/events`);
      ws.onopen = () => setEventsConnected(true);
      ws.onmessage = onMessage;
      ws.onerror = () => ws?.close();
      ws.onclose = () => {
        setEventsConnected(false);
        if (!stopped) timer = setTimeout(connect, 2000);
      };
    };

    // Check the room first so a bad code shows "not found" instead of a
    // forever-reconnecting socket.
    fetchRoom(code)
      .then(() => connect())
      .catch(() => setRoomMissing(true));

    return () => {
      stopped = true;
      clearTimeout(timer);
      ws?.close();
    };
  }, [code, loadTrace]);

  const setLanguage = useCallback(
    (l: Language) => {
      doc.getMap("meta").set("language", l);
    },
    [doc],
  );

  const run = useCallback(async () => {
    const source = doc.getText("code").toString();
    if (!source.trim()) {
      setRunError("Write or paste some code first, then run it.");
      return;
    }
    setRunState("running");
    setRunError(null);
    try {
      const res = await fetch(`${API_BASE}/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source, language, room_id: code }),
      });
      const body = await res.json();
      if (!res.ok) {
        setRunError(body?.error?.message ?? "The run failed. Try again.");
        return;
      }
      seenTraceIds.current.add(body.trace_id);
      // POST /execute already returns the full trace; no second fetch.
      setTrace(body.trace as FullTrace);
    } catch {
      setRunError("Could not reach the API. Check your connection and try again.");
    } finally {
      setRunState("idle");
    }
  }, [code, doc, language]);

  const connected = yConnected && eventsConnected;

  return {
    doc,
    awareness,
    yConnected,
    eventsConnected,
    connected,
    members,
    memberCount,
    language,
    setLanguage,
    roomMissing,
    run,
    runState,
    runError,
    trace,
  };
}
