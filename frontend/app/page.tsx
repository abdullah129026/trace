"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ROOM_CODE_RE, createRoom } from "../lib/room";

const STEPS = [
  {
    n: "1",
    title: "Create a room",
    body: "One click gives you a room code. No accounts, no setup.",
  },
  {
    n: "2",
    title: "Write code together",
    body: "Everyone edits the same file live, with each person's cursor visible.",
  },
  {
    n: "3",
    title: "Run it and inspect",
    body: "Anyone runs the shared code; the whole room gets the trace and scrubs through it.",
  },
];

export default function Home() {
  const router = useRouter();
  const [code, setCode] = useState("");
  const [joinError, setJoinError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const join = async (e: React.FormEvent) => {
    e.preventDefault();
    const clean = code.trim().toUpperCase();
    if (!ROOM_CODE_RE.test(clean)) {
      setJoinError("Room codes are 6 characters, like KQ4M9Z.");
      return;
    }
    setJoinError(null);
    setBusy(true);
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/rooms/${clean}`,
      );
      if (!res.ok) {
        setJoinError("No room with that code. Check it, or create a new one below.");
        return;
      }
      router.push(`/r/${clean}`);
    } catch {
      setJoinError("Could not reach the API. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  };

  const create = async () => {
    setBusy(true);
    try {
      const newCode = await createRoom();
      router.push(`/r/${newCode}`);
    } catch (err) {
      setJoinError(err instanceof Error ? err.message : "Could not create a room.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="mx-auto max-w-2xl px-6 py-20 sm:py-28">
      <p className="font-mono text-sm text-accent">trace</p>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight sm:text-5xl">
        Debug together, live.
      </h1>
      <p className="mt-4 max-w-xl text-lg leading-relaxed text-ink-soft">
        Paste code, share the room code, and watch it run with your team.
        Everyone sees the same steps, the same variables, the same moment it
        breaks. Python and JavaScript, in the browser.
      </p>

      <form onSubmit={join} className="mt-10 rounded-xl border border-line bg-white p-5">
        <label htmlFor="room-code" className="text-sm font-medium">
          Join a room
        </label>
        <div className="mt-2 flex gap-2">
          <input
            id="room-code"
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 6))}
            placeholder="KQ4M9Z"
            autoComplete="off"
            spellCheck={false}
            className="w-full rounded-lg border border-line bg-paper px-4 py-2.5 font-mono text-lg tracking-[0.2em] outline-none placeholder:text-ink-faint focus:border-accent"
          />
          <button
            type="submit"
            disabled={busy}
            className="shrink-0 rounded-lg bg-accent px-5 py-2.5 font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-60"
          >
            Join
          </button>
        </div>
        {joinError && <p className="mt-2 text-sm text-red-700">{joinError}</p>}
        <div className="mt-4 flex items-center gap-3 text-sm text-ink-faint">
          <span className="h-px flex-1 bg-line" />
          or
          <span className="h-px flex-1 bg-line" />
        </div>
        <button
          type="button"
          onClick={create}
          disabled={busy}
          className="mt-4 w-full rounded-lg border border-line px-4 py-2.5 font-medium text-ink transition-colors hover:border-ink-faint disabled:opacity-60"
        >
          Create a room
        </button>
      </form>

      <section className="mt-14">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">
          How it works
        </h2>
        <ol className="mt-4 space-y-5">
          {STEPS.map((s) => (
            <li key={s.n} className="flex gap-4">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-soft font-mono text-sm font-semibold text-accent">
                {s.n}
              </span>
              <div>
                <p className="font-medium">{s.title}</p>
                <p className="mt-0.5 text-sm text-ink-soft">{s.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <p className="mt-14 border-t border-line pt-6 text-xs leading-relaxed text-ink-faint">
        Trace runs on free-tier hosting. If the server is asleep, the first
        run can take half a minute while it wakes up.
      </p>
    </main>
  );
}
