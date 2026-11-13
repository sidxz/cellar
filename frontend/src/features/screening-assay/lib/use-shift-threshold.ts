"use client";

import { useCallback, useState } from "react";

const KEY = "cellar.thermalShift.threshold";
/** Thermo Fisher Protein Thermal Shift guidance. */
const DEFAULT_THRESHOLD = 2;

const valid = (t: number) => (Number.isFinite(t) && t > 0 ? t : DEFAULT_THRESHOLD);

function read(): number {
  try {
    return valid(Number(localStorage.getItem(KEY) ?? Number.NaN));
  } catch {
    return DEFAULT_THRESHOLD;
  }
}

/** The |ΔTm| display threshold (°C), one per browser. An empty or non-positive
 *  value falls back to 2. */
export function useShiftThreshold(): [number, (next: number) => void] {
  const [threshold, setThreshold] = useState(read);
  const save = useCallback((next: number) => {
    const t = valid(next);
    setThreshold(t);
    try {
      localStorage.setItem(KEY, String(t));
    } catch {
      // Storage unavailable: the threshold just doesn't persist.
    }
  }, []);
  return [threshold, save];
}
