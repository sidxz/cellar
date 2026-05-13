"use client";

import { useEffect } from "react";
import { create } from "zustand";

export interface BreadcrumbCrumb {
  label: string;
  href?: string;
}

interface BreadcrumbOverrideState {
  overrides: Map<string, string>;
  trail: BreadcrumbCrumb[] | null;
  set: (segment: string, label: string) => void;
  remove: (segment: string) => void;
  setTrail: (trail: BreadcrumbCrumb[]) => void;
  clearTrail: () => void;
}

const useBreadcrumbStore = create<BreadcrumbOverrideState>((set) => ({
  overrides: new Map(),
  trail: null,
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
  setTrail: (trail) => set({ trail }),
  clearTrail: () => set({ trail: null }),
}));

export function useBreadcrumbOverrides(): Map<string, string> {
  return useBreadcrumbStore((s) => s.overrides);
}

export function useBreadcrumbTrailValue(): BreadcrumbCrumb[] | null {
  return useBreadcrumbStore((s) => s.trail);
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

/** Declare the full breadcrumb trail for a page. Takes precedence over
 *  URL-based generation. Clears on unmount.
 *  Skips when trail is empty (e.g., entity still loading). */
export function useBreadcrumbTrail(trail: BreadcrumbCrumb[]) {
  const setTrail = useBreadcrumbStore((s) => s.setTrail);
  const clearTrail = useBreadcrumbStore((s) => s.clearTrail);
  useEffect(() => {
    if (trail.length === 0 || !trail[trail.length - 1].label) return;
    setTrail(trail);
    return () => clearTrail();
  }, [trail, setTrail, clearTrail]);
}
