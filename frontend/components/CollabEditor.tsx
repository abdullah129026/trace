"use client";

import { useEffect, useRef } from "react";
import { Compartment, EditorState } from "@codemirror/state";
import {
  EditorView,
  highlightActiveLine,
  highlightActiveLineGutter,
  keymap,
  lineNumbers,
  placeholder,
} from "@codemirror/view";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import {
  bracketMatching,
  defaultHighlightStyle,
  indentOnInput,
  syntaxHighlighting,
} from "@codemirror/language";
import { python } from "@codemirror/lang-python";
import { javascript } from "@codemirror/lang-javascript";
import { yCollab } from "y-codemirror.next";
import * as Y from "yjs";
import type { WebsocketProvider } from "y-websocket";
import type { Language } from "../lib/room";

/** Paper-and-ink CodeMirror theme: quiet chrome, emerald caret. */
const editorTheme = EditorView.theme({
  "&": {
    backgroundColor: "transparent",
    height: "100%",
  },
  ".cm-content": {
    fontFamily: "var(--font-jetbrains-mono), ui-monospace, monospace",
    fontSize: "13.5px",
    lineHeight: "1.7",
    caretColor: "#047857",
    padding: "16px 0",
  },
  ".cm-line": {
    padding: "0 16px",
  },
  ".cm-activeLine": {
    backgroundColor: "#f5f5f4",
  },
  ".cm-activeLineGutter": {
    backgroundColor: "transparent",
  },
  ".cm-gutters": {
    backgroundColor: "transparent",
    borderRight: "1px solid #e7e5e4",
    color: "#a8a29e",
    fontFamily: "var(--font-jetbrains-mono), ui-monospace, monospace",
    fontSize: "12px",
  },
  ".cm-selectionBackground": {
    backgroundColor: "#d6f5e3 !important",
  },
  "&.cm-focused": {
    outline: "none",
  },
  // Remote collaborator carets and selections (rendered by y-codemirror).
  ".cm-ySelectionCaret": {
    width: "2px",
    marginLeft: "-1px",
  },
  ".cm-ySelectionInfo": {
    fontFamily: "var(--font-inter), sans-serif",
    fontSize: "11px",
    padding: "1px 6px",
    borderRadius: "4px",
    color: "#fff",
    opacity: "0.9",
  },
});

function languageExtension(language: Language) {
  return language === "python" ? python() : javascript();
}

interface Props {
  doc: Y.Doc;
  awareness: WebsocketProvider["awareness"] | null;
  language: Language;
}

/**
 * The shared editor. Text lives in the Yjs doc under the "code" key and
 * syncs through the relay; remote cursors render from awareness states.
 */
export function CollabEditor({ doc, awareness, language }: Props) {
  const mountRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const langCompartment = useRef(new Compartment());

  useEffect(() => {
    if (!mountRef.current || !awareness) return;
    const ytext = doc.getText("code");
    const view = new EditorView({
      state: EditorState.create({
        doc: ytext.toString(),
        extensions: [
          lineNumbers(),
          highlightActiveLineGutter(),
          highlightActiveLine(),
          history(),
          keymap.of([...defaultKeymap, ...historyKeymap]),
          indentOnInput(),
          bracketMatching(),
          syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
          langCompartment.current.of(languageExtension(language)),
          yCollab(ytext, awareness),
          editorTheme,
          EditorView.lineWrapping,
          placeholder(
            "Paste or write code here. Anyone with the room code edits with you, live.",
          ),
        ],
      }),
      parent: mountRef.current,
    });
    viewRef.current = view;
    return () => {
      view.destroy();
      viewRef.current = null;
    };
    // Mount once per doc+awareness; language switches reconfigure below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doc, awareness]);

  useEffect(() => {
    viewRef.current?.dispatch({
      effects: langCompartment.current.reconfigure(languageExtension(language)),
    });
  }, [language]);

  return <div ref={mountRef} className="h-full min-h-[420px] text-left" />;
}
