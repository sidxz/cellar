"use client";

import { useCallback, useState } from "react";
import { useSearchParams } from "next/navigation";
import type { UmapPicker } from "@/features/sar-analysis/types";

/**
 * URL state for the UMAP diversity-picker algorithm and its parameters.
 *
 * Supported pickers:
 * - "maxmin"  — MaxMin (Kennard-Stone) picker.  Parameter: n (int, default 50).
 * - "butina"  — Butina (leader) clustering.      Parameter: t (float, default 0.4).
 *
 * Local React state is the source of truth so toggles work in tests / jsdom
 * without a full router round-trip.  The URL is updated as a side-effect via
 * window.history.replaceState so deep-linked URLs land in the correct config
 * on mount.
 *
 * URL shape:
 *   ?picker=maxmin&n=50
 *   ?picker=butina&t=0.4
 */

const DEFAULT_PICKER: UmapPicker = "maxmin";
const DEFAULT_THRESHOLD = 0.4;

/**
 * Size-adaptive default for N: ~10% of the compound set, clamped to [5, 50].
 * - 22 mols → 5 (floor)
 * - 100 mols → 10
 * - 500 mols → 50 (ceiling)
 * - 5K mols → 50 (ceiling)
 *
 * Chemists rarely advance more than ~50 representatives in a single workflow,
 * and below ~5 the diverse-subset value is questionable. The 10% midpoint
 * mirrors the medchem rule-of-thumb for diverse-subset screening sizes.
 */
export function defaultNForSize(collectionSize: number): number {
  const ratio = Math.ceil(collectionSize * 0.1);
  return Math.max(5, Math.min(50, ratio));
}

interface PickerConfig {
  picker: UmapPicker;
  n: number;
  threshold: number;
  setPicker: (p: UmapPicker) => void;
  setN: (val: number) => void;
  setThreshold: (val: number) => void;
}

interface UsePickerConfigOptions {
  /** Compound set size — drives the size-adaptive default N. */
  collectionSize?: number;
}

function writeUrl(updates: Record<string, string | null>): void {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  for (const [k, v] of Object.entries(updates)) {
    if (v == null) url.searchParams.delete(k);
    else url.searchParams.set(k, v);
  }
  window.history.replaceState({}, "", url.toString());
}

export function usePickerConfig(opts: UsePickerConfigOptions = {}): PickerConfig {
  const params = useSearchParams();
  const sizeDefault = opts.collectionSize
    ? defaultNForSize(opts.collectionSize)
    : 10;

  // Read URL once on mount; subsequent state is React-owned.
  const [picker, setPicker_] = useState<UmapPicker>(() => {
    const raw = params.get("picker");
    return raw === "butina" ? "butina" : DEFAULT_PICKER;
  });
  const [n, setN_] = useState<number>(() => {
    const raw = params.get("n");
    return raw ? Number(raw) : sizeDefault;
  });
  const [threshold, setThreshold_] = useState<number>(() => {
    const raw = params.get("t");
    return raw ? Number(raw) : DEFAULT_THRESHOLD;
  });

  const setPicker = useCallback(
    (p: UmapPicker) => {
      setPicker_(p);
      if (p === "maxmin") {
        setN_(sizeDefault);
        setThreshold_(DEFAULT_THRESHOLD);
        writeUrl({ picker: "maxmin", t: null, n: String(sizeDefault) });
      } else {
        setThreshold_(DEFAULT_THRESHOLD);
        setN_(sizeDefault);
        writeUrl({ picker: "butina", n: null, t: String(DEFAULT_THRESHOLD) });
      }
    },
    [sizeDefault],
  );

  const setN = useCallback((val: number) => {
    setN_(val);
    writeUrl({ n: String(val) });
  }, []);

  const setThreshold = useCallback((val: number) => {
    setThreshold_(val);
    writeUrl({ t: String(val) });
  }, []);

  return { picker, n, threshold, setPicker, setN, setThreshold };
}
