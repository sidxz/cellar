"use client";

import { useCallback, useMemo, useState } from "react";

interface Stored {
  /** Columns the viewer hid. */
  hidden: string[];
  /** Columns the viewer showed: an empty column stays shown once ticked. */
  shown: string[];
}

function read(key: string): Stored {
  try {
    const raw = JSON.parse(localStorage.getItem(key) ?? "{}") as Partial<Stored>;
    return {
      hidden: Array.isArray(raw.hidden) ? raw.hidden.filter((x) => typeof x === "string") : [],
      shown: Array.isArray(raw.shown) ? raw.shown.filter((x) => typeof x === "string") : [],
    };
  } catch {
    return { hidden: [], shown: [] };
  }
}

/** Which of a campaign's optional columns this viewer hides, kept per campaign in this browser.
 *  A column in ``empty`` (no value anywhere yet) starts hidden until the viewer shows it; one that
 *  gains values shows by itself, unless the viewer hid it. Column ids are the grid's: "structure",
 *  "notes", a channel id (its value), and "<channel id>:curve". */
export function useColumnVisibility(campaignId: string, empty: readonly string[]) {
  const key = `campaign-columns:${campaignId}`;
  const [stored, setStored] = useState(() => ({ key, ...read(key) }));
  // Another campaign in the same mounted grid reads its own choice.
  const current = stored.key === key ? stored : { key, ...read(key) };
  if (current !== stored) setStored(current);

  const hidden = useMemo(() => {
    const shown = new Set(current.shown);
    return new Set([...current.hidden, ...empty.filter((id) => !shown.has(id))]);
  }, [current, empty]);

  const setVisible = useCallback(
    (ids: string[], visible: boolean) =>
      setStored((prev) => {
        const hiddenIds = new Set(prev.hidden);
        const shownIds = new Set(prev.shown);
        for (const id of ids) {
          if (visible) {
            hiddenIds.delete(id);
            shownIds.add(id);
          } else {
            hiddenIds.add(id);
            shownIds.delete(id);
          }
        }
        const next = { key: prev.key, hidden: [...hiddenIds], shown: [...shownIds] };
        try {
          localStorage.setItem(
            prev.key,
            JSON.stringify({ hidden: next.hidden, shown: next.shown }),
          );
        } catch {
          // Storage unavailable: the choice holds for this visit only.
        }
        return next;
      }),
    [],
  );

  return { hidden, setVisible };
}
