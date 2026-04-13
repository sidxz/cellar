"use client";

import { useEffect } from "react";
import { create } from "zustand";

interface BreadcrumbOverrideState {
  overrides: Map<string, string>;
  set: (segment: string, label: string) => void;
  remove: (segment: string) => void;
}

const useBreadcrumbStore = create<BreadcrumbOverrideState>((set) => ({
  overrides: new Map(),
  set: (segment, label) =>
    set((state) => {
      const next = new Map(state.overrides);
      next.set(segment, label);
      return { overrides: next };
    }),
  remove: (segment) =>
    set((state) => {
      const next = new Map(state.overrides);
      next.delete(segment);
      return { overrides: next };
    }),
}));

export function useBreadcrumbOverrides(): Map<string, string> {
  return useBreadcrumbStore((s) => s.overrides);
}

/** Set a breadcrumb override for a URL segment. Clears on unmount.
 *  Skips when label is empty (e.g., entity still loading). */
export function useBreadcrumbOverride(segment: string, label: string) {
  const setBreadcrumb = useBreadcrumbStore((s) => s.set);
  const removeBreadcrumb = useBreadcrumbStore((s) => s.remove);
  useEffect(() => {
    if (!segment || !label) return;
    setBreadcrumb(segment, label);
    return () => removeBreadcrumb(segment);
  }, [segment, label, setBreadcrumb, removeBreadcrumb]);
}
