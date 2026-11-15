"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@astryxdesign/core/Button";
import { TextInput } from "@astryxdesign/core/TextInput";
import { askTrace, explainStep } from "../lib/room";
import type { FullTrace } from "../lib/trace";

/** AI co-pilot panel, pinned to the visualizer's selected step. The
 *  explanation always names the step it explains; when the playhead
 *  moves on, the panel says so instead of pretending the old answer
 *  still applies. Explanations render as text, never HTML. Voice uses
 *  only the browser's built-in speech synthesis, no server TTS. */
export function CopilotPanel({
  trace,
  traceId,
  stepIndex,
}: {
  trace: FullTrace;
  traceId: string | null;
  stepIndex: number;
}) {
  const [explanation, setExplanation] = useState<string | null>(null);
  const [explainedStep, setExplainedStep] = useState<number | null>(null);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [speaking, setSpeaking] = useState(false);
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

  const step = trace.steps[stepIndex];
  const voiceSupported =
    typeof window !== "undefined" && "speechSynthesis" in window;

  const stopSpeaking = () => {
    if (voiceSupported) window.speechSynthesis.cancel();
    utteranceRef.current = null;
    setSpeaking(false);
  };

  // Never keep reading an old explanation after the panel unmounts.
  useEffect(
    () => () => {
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    },
    [],
  );

  const runQuery = async (ask: boolean) => {
    if (!traceId || !step) return;
    stopSpeaking();
    setBusy(true);
    setError(null);
    try {
      const body = ask
        ? await askTrace(traceId, stepIndex, question.trim())
        : await explainStep(traceId, stepIndex);
      setExplanation(body.explanation);
      setExplainedStep(stepIndex);
      if (ask) setQuestion("");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "The co-pilot could not answer. Try again.",
      );
    } finally {
      setBusy(false);
    }
  };

  const toggleVoice = () => {
    if (!explanation || !voiceSupported) return;
    if (speaking) {
      stopSpeaking();
      return;
    }
    const utterance = new SpeechSynthesisUtterance(explanation);
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    utteranceRef.current = utterance;
    window.speechSynthesis.speak(utterance);
    setSpeaking(true);
  };

  const stale = explainedStep !== null && explainedStep !== stepIndex;

  return (
    <div className="border-t border-line px-5 py-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">
          Co-pilot
        </h3>
        <p className="font-mono text-xs text-ink-soft">
          Step {stepIndex + 1} of {trace.steps.length}
          {step ? ` · line ${step.line}` : ""}
        </p>
      </div>

      {!traceId ? (
        <p className="mt-3 text-sm text-ink-faint">
          Run the code first, then the co-pilot can explain a step.
        </p>
      ) : (
        <>
          <div className="mt-3">
            <Button
              label={busy ? "Asking…" : "Explain this step"}
              variant="primary"
              onClick={() => void runQuery(false)}
              isDisabled={busy}
            />
          </div>
          <form
            className="mt-3 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (question.trim()) void runQuery(true);
            }}
          >
            <div className="w-full">
              <TextInput
                label="Ask the trace a question"
                isLabelHidden
                value={question}
                onChange={(value) => setQuestion(value)}
                placeholder="Ask about this step, for example why is this None?"
                aria-label="Ask the trace a question"
              />
            </div>
            <div className="shrink-0">
              <Button
                type="submit"
                label="Ask"
                variant="secondary"
                isDisabled={busy || !question.trim()}
              />
            </div>
          </form>
        </>
      )}

      {error && (
        <p className="mt-3 rounded-lg bg-error-soft px-3 py-2 text-sm text-error">
          {error}
        </p>
      )}

      {stale && explanation && (
        <p className="mt-3 text-xs text-ink-faint">
          This explains step {explainedStep + 1}, not the current step.
          Press Explain this step for step {stepIndex + 1}.
        </p>
      )}

      {explanation && (
        <div className="mt-3 rounded-lg bg-paper px-4 py-3">
          <p className="text-sm leading-relaxed text-ink">{explanation}</p>
          {voiceSupported && (
            <div className="mt-2">
              <Button
                label={speaking ? "Stop narration" : "Read it aloud"}
                variant="secondary"
                size="sm"
                onClick={toggleVoice}
              />
            </div>
          )}
        </div>
      )}
      {!explanation && !error && traceId && (
        <p className="mt-3 text-sm text-ink-faint">
          Press Explain this step, or ask a question about it. The answer
          uses only the values in this trace.
        </p>
      )}
    </div>
  );
}
