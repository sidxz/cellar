"use client";

import { useCallback, useEffect, useState } from "react";

export interface RunResultsView {
  diagnostics: boolean;
  compact: boolean;
  unit: "native" | "uM" | "nM";
}

const DEFAULT_VIEW: RunResultsView = { diagnostics: false, compact: false, unit: "native" };

/** Presentation choices only; fitting, classifications, and hit criteria keep their stored units. */
export function useRunResultsView(protocolId: string) {
  const storageKey = `cellar.run-results.view.${protocolId}`;
  const [view, setView] = useState<RunResultsView>(DEFAULT_VIEW);

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) ?? "null");
      setView({
        diagnostics: saved?.diagnostics === true,
        compact: saved?.compact === true,
        unit: saved?.unit === "uM" || saved?.unit === "nM" ? saved.unit : "native",
      });
    } catch {
      setView(DEFAULT_VIEW);
    }
  }, [storageKey]);

  const updateView = useCallback(
    (next: RunResultsView) => {
      setView(next);
      try {
        localStorage.setItem(storageKey, JSON.stringify(next));
      } catch {
        // The controls still work when browser storage is unavailable.
      }
    },
    [storageKey],
  );

  return [view, updateView] as const;
}

const MICROMOLAR_SCALE: Record<string, number> = {
  M: 1e6,
  mM: 1e3,
  uM: 1,
  nM: 1e-3,
  pM: 1e-6,
};

export function normalizeDoseUnit(unit: string) {
  return unit.trim().replace(/[µμ]/g, "u");
}

export function displayDoseUnit(unit: string) {
  return normalizeDoseUnit(unit) === "uM" ? "µM" : unit;
}

export function doseUnitScale(source: string, target: string): number {
  const from = MICROMOLAR_SCALE[normalizeDoseUnit(source)];
  const to = MICROMOLAR_SCALE[normalizeDoseUnit(target)];
  return from != null && to != null ? from / to : 1;
}

export function isConvertibleDoseUnit(unit: string) {
  return Object.hasOwn(MICROMOLAR_SCALE, normalizeDoseUnit(unit));
}
