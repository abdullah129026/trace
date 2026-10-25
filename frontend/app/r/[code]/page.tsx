"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { CollabEditor } from "../../../components/CollabEditor";
import { TraceVisualizer } from "../../../components/TraceVisualizer";
import { useRoom } from "../../../lib/useRoom";
import {
  LANGUAGES,
  Language,
  ROOM_CODE_RE,
  inviteLink,
} from "../../../lib/room";

export default function RoomPage({ params }: { params: Promise<{ code: string }> }) {
  const { code: rawCode } = use(params);
  const code = rawCode.toUpperCase();
  const valid = ROOM_CODE_RE.test(code);

  const {
    doc,
    awareness,
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
  } = useRoom(valid ? code : "------");

  const [copied, setCopied] = useState(false);

  const copyInvite = async () => {
    try {
      await navigator.clipboard.writeText(inviteLink(code));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard unavailable; the code itself is visible to copy by hand.
    }
  };

  useEffect(() => {
    document.title = valid ? `Trace · Room ${code}` : "Trace";
  }, [code, valid]);

  if (!valid) {
    return (
      <main className="mx-auto max-w-xl px-6 py-24 text-center">
        <p className="font-mono text-sm text-ink-faint">room code</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">
          That code does not look right
        </h1>
        <p className="mt-3 text-ink-soft">
          Room codes are 6 characters, like <span className="font-mono">KQ4M9Z</span>.
        </p>
        <Link href="/" className="mt-6 inline-block text-accent underline underline-offset-4">
          Back to the entrance
        </Link>
      </main>
    );
  }

  if (roomMissing) {
    return (
      <main className="mx-auto max-w-xl px-6 py-24 text-center">
        <p className="font-mono text-sm text-ink-faint">{code}</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">
          No room with this code
        </h1>
        <p className="mt-3 text-ink-soft">
          It may have expired when the server restarted. Create a fresh one and
          share the new code.
        </p>
        <Link href="/" className="mt-6 inline-block text-accent underline underline-offset-4">
          Back to the entrance
        </Link>
      </main>
    );
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-line">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-6 py-3">
          <Link href="/" className="text-lg font-semibold tracking-tight">
            Trace
          </Link>
          <button
            onClick={copyInvite}
            title="Copy invite link"
            className="rounded-md border border-line bg-white px-2.5 py-1 font-mono text-sm tracking-widest text-ink transition-colors hover:border-ink-faint"
          >
            {code}
          </button>
          <span className="hidden text-xs text-ink-faint sm:inline">
            {copied ? "Invite link copied" : "Click the code to copy the invite link"}
          </span>
          <div className="ml-auto flex items-center gap-4">
            <div className="flex items-center gap-2" title="People in this room">
              <span className="flex -space-x-1.5">
                {members.slice(0, 5).map((m) => (
                  <span
                    key={m.clientId}
                    className="h-5 w-5 rounded-full border-2 border-paper"
                    style={{ backgroundColor: m.color }}
                    title={m.name}
                  />
                ))}
              </span>
              <span className="text-sm text-ink-soft">
                {memberCount} here
              </span>
            </div>
            <span className="flex items-center gap-1.5 text-sm text-ink-soft">
              <span
                className={`h-2 w-2 rounded-full ${connected ? "bg-accent" : "bg-amber-500"}`}
              />
              {connected ? "Live" : "Connecting"}
            </span>
          </div>
        </div>
      </header>

      <main className="mx-auto grid w-full max-w-6xl flex-1 gap-6 px-6 py-6 lg:grid-cols-[1fr_340px]">
        <section className="overflow-hidden rounded-xl border border-line bg-white">
          <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
            <div className="flex items-center gap-1 rounded-lg bg-paper p-1" role="group" aria-label="Language (shared)">
              {LANGUAGES.map((l: Language) => (
                <button
                  key={l}
                  onClick={() => setLanguage(l)}
                  className={`rounded-md px-3 py-1 text-sm transition-colors ${
                    language === l
                      ? "bg-white font-medium text-ink shadow-sm"
                      : "text-ink-soft hover:text-ink"
                  }`}
                >
                  {l === "python" ? "Python" : "JavaScript"}
                </button>
              ))}
            </div>
            <span className="text-xs text-ink-faint">shared with the room</span>
          </div>
          {!awareness ? (
            <div className="flex h-[420px] items-center justify-center text-sm text-ink-faint">
              Joining the room…
            </div>
          ) : (
            <CollabEditor doc={doc} awareness={awareness} language={language} />
          )}
        </section>

        <aside className="flex flex-col gap-6">
          <section className="rounded-xl border border-line bg-white p-5">
            <button
              onClick={run}
              disabled={runState === "running"}
              className="w-full rounded-lg bg-accent px-4 py-2.5 font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-wait disabled:opacity-60"
            >
              {runState === "running" ? "Running…" : "Run"}
            </button>
            <p className="mt-3 text-xs leading-relaxed text-ink-faint">
              Runs the shared editor code in the sandbox. Everyone in the room
              receives the trace.
            </p>
            {runError && (
              <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
                {runError}
              </p>
            )}
          </section>

          <section className="rounded-xl border border-line bg-white p-5">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">
              In this room
            </h2>
            <ul className="mt-3 space-y-2">
              {members.map((m) => (
                <li key={m.clientId} className="flex items-center gap-2.5 text-sm">
                  <span
                    className="h-3 w-3 rounded-full"
                    style={{ backgroundColor: m.color }}
                  />
                  <span className={m.self ? "font-medium" : "text-ink-soft"}>
                    {m.name}
                    {m.self ? " (you)" : ""}
                  </span>
                </li>
              ))}
              {members.length === 0 && (
                <li className="text-sm text-ink-faint">Finding everyone…</li>
              )}
            </ul>
          </section>
        </aside>
      </main>

      <div className="mx-auto w-full max-w-6xl px-6 pb-10">
        {trace ? (
          <TraceVisualizer trace={trace} />
        ) : (
          <section className="rounded-xl border border-line bg-white p-5">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">
              Trace
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-ink-soft">
              No runs yet. Press Run and the trace visualizer lands here for
              everyone in the room.
            </p>
          </section>
        )}
      </div>
    </div>
  );
}
