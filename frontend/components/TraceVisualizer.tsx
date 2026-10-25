"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  FullTrace,
  clampStep,
  formatSnapshot,
  graphPoints,
  stepIntervalMs,
} from "../lib/trace";

const SPEEDS = [0.5, 1, 2, 4];

/** Execution visualizer: graph, source line, variables, stack, stdout,
 *  and the timeline scrubber along the bottom. Every number and value
 *  comes from the fetched trace; values render as text, never HTML. */
export function TraceVisualizer({ trace }: { trace: FullTrace }) {
  const steps = trace.steps;
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  // A new trace resets the playhead to the first step.
  useEffect(() => {
    setStep(0);
    setPlaying(false);
  }, [trace]);

  useEffect(() => {
    if (!playing || steps.length === 0) return;
    timer.current = setInterval(() => {
      setStep((s) => {
        if (s >= steps.length - 1) {
          setPlaying(false);
          return s;
        }
        return s + 1;
      });
    }, stepIntervalMs(speed));
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [playing, speed, steps.length]);

  const current = steps.length > 0 ? steps[clampStep(step, steps.length)] : null;
  const points = useMemo(
    () => graphPoints(steps, 560, 160),
    [steps],
  );
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x},${p.y}`).join(" ");
  const currentPoint = current ? points[clampStep(step, steps.length)] : null;

  const go = (delta: number) => {
    setPlaying(false);
    setStep((s) => clampStep(s + delta, steps.length));
  };

  const onScrubberKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowRight") {
      e.preventDefault();
      go(1);
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      go(-1);
    }
  };

  if (steps.length === 0) {
    return (
      <section className="rounded-xl border border-line bg-white p-5">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">
          Trace
        </h2>
        <p className="mt-3 text-sm leading-relaxed text-ink-soft">
          The run finished but captured no steps. Check the source and run it
          again.
        </p>
      </section>
    );
  }

  // Dunder names are interpreter furniture, not the user's variables.
  const locals = current
    ? Object.entries(current.locals).filter(
        ([name]) => !(name.startsWith("__") && name.endsWith("__")),
      )
    : [];
  const changedNote =
    trace.result.status === "error" && trace.result.error
      ? trace.result.error
      : null;

  return (
    <section className="overflow-hidden rounded-xl border border-line bg-white">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">
          Trace
        </h2>
        <p className="font-mono text-xs text-ink-soft">
          {steps.length} steps · {trace.language}
          {trace.result.truncated ? " · stopped at the step cap" : ""}
        </p>
      </div>

      {changedNote && (
        <p className="border-b border-line bg-red-50 px-5 py-3 text-sm text-red-700">
          {changedNote}
        </p>
      )}
      {trace.result.truncated && (
        <p className="border-b border-line bg-amber-50 px-5 py-3 text-xs text-amber-800">
          The trace stopped at the step cap instead of dropping steps silently.
          The cap is one edit in the backend config.
        </p>
      )}

      <div className="grid gap-0 lg:grid-cols-[1fr_300px]">
        <div className="border-b border-line lg:border-b-0 lg:border-r">
          <div className="border-b border-line px-5 py-3">
            <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">
              Execution graph
            </p>
            <p className="mt-1 text-xs text-ink-faint">
              Left to right is time. Each row is a source line; the path
              revisiting a row is a loop.
            </p>
          </div>
          <svg
            viewBox="0 0 560 160"
            className="block w-full"
            role="img"
            aria-label={`Execution graph with ${steps.length} steps`}
          >
            {path && (
              <path d={path} fill="none" stroke="#d6d3d1" strokeWidth="1.5" />
            )}
            {currentPoint && (
              <circle
                cx={currentPoint.x}
                cy={currentPoint.y}
                r="6"
                fill="#047857"
              />
            )}
          </svg>
          <div className="border-t border-line px-5 py-3">
            <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">
              Source · line {current?.line ?? "—"}
            </p>
            <div className="mt-2 overflow-x-auto font-mono text-sm leading-6">
              {trace.source_lines.map((src, idx) => {
                const lineNo = idx + 1;
                const isCurrent = current?.line === lineNo;
                return (
                  <div
                    key={lineNo}
                    className={`flex gap-3 whitespace-pre rounded px-2 ${
                      isCurrent ? "bg-accent-soft font-medium text-ink" : "text-ink-soft"
                    }`}
                  >
                    <span className="w-8 shrink-0 text-right text-ink-faint">
                      {lineNo}
                    </span>
                    <span>{src || " "}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        <div>
          <div className="border-b border-line px-5 py-3">
            <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">
              Variables at this step
            </p>
            {locals.length === 0 ? (
              <p className="mt-2 text-sm text-ink-faint">
                No variables in scope here.
              </p>
            ) : (
              <dl className="mt-2 space-y-1.5 font-mono text-sm">
                {locals.map(([name, value]) => (
                  <div key={name} className="flex gap-2">
                    <dt className="shrink-0 text-ink">{name}</dt>
                    <dd className="break-all text-ink-soft">
                      {formatSnapshot(value)}
                    </dd>
                  </div>
                ))}
              </dl>
            )}
          </div>
          <div className="border-b border-line px-5 py-3">
            <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">
              Stack
            </p>
            {!current || current.stack.length === 0 ? (
              <p className="mt-2 text-sm text-ink-faint">
                No frames on the stack at this step.
              </p>
            ) : (
              <ol className="mt-2 space-y-1 font-mono text-sm text-ink-soft">
                {current.stack.map((frame, i) => (
                  <li key={`${i}-${frame}`}>
                    <span className="text-ink-faint">{i + 1}.</span> {frame}
                  </li>
                ))}
              </ol>
            )}
            {current && (
              <p className="mt-2 text-xs text-ink-faint">
                Event: {current.event}
              </p>
            )}
          </div>
          <div className="px-5 py-3">
            <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">
              Output so far
            </p>
            {current?.stdout_so_far ? (
              <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-words font-mono text-sm text-ink-soft">
                {current.stdout_so_far}
              </pre>
            ) : (
              <p className="mt-2 text-sm text-ink-faint">
                Nothing printed yet at this step.
              </p>
            )}
          </div>
        </div>
      </div>

      <div
        className="border-t border-line px-5 py-4"
        tabIndex={0}
        onKeyDown={onScrubberKey}
        aria-label="Timeline scrubber. Use left and right arrow keys to step."
      >
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={() => go(-1)}
            disabled={step <= 0}
            className="rounded-lg border border-line px-3 py-1.5 text-sm transition-colors hover:border-ink-faint disabled:opacity-40"
          >
            Prev step
          </button>
          <button
            onClick={() => setPlaying((p) => !p)}
            className="rounded-lg bg-accent px-4 py-1.5 text-sm font-medium text-white transition-opacity hover:opacity-90"
          >
            {playing ? "Pause" : "Play"}
          </button>
          <button
            onClick={() => go(1)}
            disabled={step >= steps.length - 1}
            className="rounded-lg border border-line px-3 py-1.5 text-sm transition-colors hover:border-ink-faint disabled:opacity-40"
          >
            Next step
          </button>
          <div className="flex items-center gap-1" role="group" aria-label="Playback speed">
            {SPEEDS.map((s) => (
              <button
                key={s}
                onClick={() => setSpeed(s)}
                className={`rounded-md px-2 py-1 font-mono text-xs ${
                  speed === s
                    ? "bg-accent-soft font-medium text-accent"
                    : "text-ink-soft hover:text-ink"
                }`}
              >
                {s}x
              </button>
            ))}
          </div>
          <p className="ml-auto font-mono text-xs text-ink-soft">
            Step {step + 1} of {steps.length} · line {current?.line}
          </p>
        </div>
        <input
          type="range"
          min={0}
          max={steps.length - 1}
          value={step}
          onChange={(e) => {
            setPlaying(false);
            setStep(clampStep(Number(e.target.value), steps.length));
          }}
          className="mt-3 w-full accent-[#047857]"
          aria-label="Scrub through the trace"
        />
        <p className="mt-1 text-xs text-ink-faint">
          Click the timeline to focus it, then step with the arrow keys.
        </p>
      </div>
    </section>
  );
}
