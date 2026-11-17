"use client";

import { useEffect, useMemo, useRef } from "react";
import { CommandPalette } from "@astryxdesign/core/CommandPalette";
import { createStaticSource } from "@astryxdesign/core/Typeahead";
import type { SearchableItem } from "@astryxdesign/core/Typeahead";

/** One command in the palette: an action that already exists elsewhere
 *  in the app, reachable by keyboard. The palette never invents actions. */
export interface PaletteCommand {
  id: string;
  label: string;
  group: string;
  keywords?: string[];
  run: () => void;
}

/** Cmd/Ctrl+K opens the palette. One listener per mount; the callback
 *  is read through a ref so the listener is never re-registered. */
export function useCommandPaletteHotkey(onOpen: () => void) {
  const ref = useRef(onOpen);
  ref.current = onOpen;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        ref.current();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}

type PaletteItem = SearchableItem<{ group: string }>;

/** Thin wrapper over Astryx CommandPalette for a static command list.
 *  Choosing a command runs it and closes the palette. */
export function CommandPaletteMenu({
  isOpen,
  onOpenChange,
  commands,
}: {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  commands: PaletteCommand[];
}) {
  const source = useMemo(
    () =>
      createStaticSource<PaletteItem>(
        commands.map((c) => ({
          id: c.id,
          label: c.label,
          auxiliaryData: { group: c.group },
        })),
        {
          keywords: (item) =>
            commands.find((c) => c.id === item.id)?.keywords ?? [],
        },
      ),
    [commands],
  );

  return (
    <CommandPalette
      isOpen={isOpen}
      onOpenChange={onOpenChange}
      searchSource={source}
      onValueChange={(value) => {
        commands.find((c) => c.id === value)?.run();
        onOpenChange(false);
      }}
      emptySearchText="No matching command"
      emptyBootstrapText="Type to search commands"
    />
  );
}
