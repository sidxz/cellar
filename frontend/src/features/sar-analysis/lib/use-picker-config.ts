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
const DEFAULT_N = 50;
const DEFAULT_THRESHOLD = 0.4;

interface PickerConfig {
  picker: UmapPicker;
  n: number;
  threshold: number;
  setPicker: (p: UmapPicker) => void;
  setN: (val: number) => void;
  setThreshold: (val: number) => void;
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

export function usePickerConfig(): PickerConfig {
  const params = useSearchParams();

  // Read URL once on mount; subsequent state is React-owned.
  const [picker, setPicker_] = useState<UmapPicker>(() => {
    const raw = params.get("picker");
    return raw === "butina" ? "butina" : DEFAULT_PICKER;
  });
  const [n, setN_] = useState<number>(() => {
    const raw = params.get("n");
    return raw ? Number(raw) : DEFAULT_N;
  });
  const [threshold, setThreshold_] = useState<number>(() => {
    const raw = params.get("t");
    return raw ? Number(raw) : DEFAULT_THRESHOLD;
  });

  const setPicker = useCallback((p: UmapPicker) => {
    setPicker_(p);
    if (p === "maxmin") {
      setN_(DEFAULT_N);
      setThreshold_(DEFAULT_THRESHOLD);
      writeUrl({ picker: "maxmin", t: null, n: String(DEFAULT_N) });
    } else {
      setThreshold_(DEFAULT_THRESHOLD);
      setN_(DEFAULT_N);
      writeUrl({ picker: "butina", n: null, t: String(DEFAULT_THRESHOLD) });
    }
  }, []);

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
