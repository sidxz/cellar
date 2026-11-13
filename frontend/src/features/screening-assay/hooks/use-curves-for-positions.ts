"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { CurveSeriesData } from "../lib/curve-plot";
import { CURVES_PER_REQUEST, MAX_DRAWN } from "../lib/curve-selection";
import type { MeasuredCurvesBatch } from "../types";
import type { CurveView } from "./use-run-curves";

/** One (signal, view, window asked for). `fetched` holds each position asked
 *  for: its curve, or null when the API has none. `window` is the window the
 *  first answer stated; every later request of the generation sends it. */
interface Generation {
  key: string;
  channel: string;
  view: CurveView;
  askedWindow: number | undefined;
  fetched: Map<string, CurveSeriesData | null>;
  window: number | null;
}

interface Shown {
  curves: ReadonlyMap<string, CurveSeriesData>;
  window: number | null;
}

const NOTHING: Shown = { curves: new Map(), window: null };

function shownOf(g: Generation): Shown {
  const curves = new Map<string, CurveSeriesData>();
  for (const [id, c] of g.fetched) if (c) curves.set(id, c);
  return { curves, window: g.window };
}

/** The curves of the given positions for one signal and view, fetched with
 *  POST /api/v1/measured-curves:batch in requests of CURVES_PER_REQUEST, one
 *  after another. What was fetched is kept, so a change of selection asks
 *  only for what is new; a change of signal, view or window starts again, and
 *  answers to the earlier one are dropped. The previous curves stay on screen
 *  until the first answer of the new signal, view or window. Above MAX_DRAWN
 *  positions nothing is asked for. */
export function useCurvesForPositions(
  wellIds: readonly string[],
  params: { channel: string | undefined; view: CurveView; window: number | undefined },
): {
  curves: ReadonlyMap<string, CurveSeriesData>;
  window: number | null;
  pending: boolean;
  failed: boolean;
  tooMany: boolean;
  /** Asks again for what is still missing. */
  retry: () => void;
} {
  const { channel, view, window: askedWindow } = params;
  const tooMany = wellIds.length > MAX_DRAWN;
  // Strings, so a list or params object rebuilt each render does not refire the effect.
  const genKey = `${channel}\n${view}\n${askedWindow ?? ""}`;
  const idsKey = tooMany ? "" : wellIds.join("\n");

  const gen = useRef<Generation | null>(null);
  const wanted = useRef<readonly string[]>([]);
  const running = useRef(false);
  const alive = useRef(true);
  const [shown, setShown] = useState<Shown>(NOTHING);
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);

  // One loop at a time: each turn asks for the next missing chunk of the
  // current generation and selection, so requests go out one after another.
  const pump = useCallback(async () => {
    if (running.current) return;
    running.current = true;
    setPending(true);
    setFailed(false);
    try {
      while (alive.current) {
        const g = gen.current;
        if (!g) break;
        const missing = wanted.current
          .filter((id) => !g.fetched.has(id))
          .slice(0, CURVES_PER_REQUEST);
        if (missing.length === 0) break;
        let res: MeasuredCurvesBatch;
        try {
          res = await customInstance<MeasuredCurvesBatch>({
            url: `${API_V1}/measured-curves:batch`,
            method: "POST",
            data: {
              well_ids: missing,
              channel: g.channel,
              view: g.view,
              window: g.view === "derivative" ? (g.window ?? g.askedWindow ?? null) : null,
            },
          });
        } catch {
          if (gen.current !== g) continue;
          if (alive.current) setFailed(true);
          break;
        }
        // An answer to an earlier signal, view or window.
        if (gen.current !== g) continue;
        for (const c of res.curves) g.fetched.set(c.well_id, c);
        for (const id of missing) if (!g.fetched.has(id)) g.fetched.set(id, null);
        if (g.window === null) g.window = res.window ?? null;
        if (alive.current) setShown(shownOf(g));
      }
    } finally {
      running.current = false;
      if (alive.current) setPending(false);
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  useEffect(() => {
    wanted.current = idsKey ? idsKey.split("\n") : [];
    if (gen.current?.key !== genKey) {
      gen.current = channel
        ? { key: genKey, channel, view, askedWindow, fetched: new Map(), window: null }
        : null;
      // Nothing to wait for: do not keep showing the earlier curves.
      if (wanted.current.length === 0) setShown(NOTHING);
    }
    const g = gen.current;
    // A failure is about curves still missing; with none missing it is over.
    if (!g || wanted.current.every((id) => g.fetched.has(id))) setFailed(false);
    if (g && wanted.current.length > 0) void pump();
  }, [genKey, idsKey, channel, view, askedWindow, pump]);

  const retry = useCallback(() => void pump(), [pump]);

  return { curves: shown.curves, window: shown.window, pending, failed, tooMany, retry };
}
