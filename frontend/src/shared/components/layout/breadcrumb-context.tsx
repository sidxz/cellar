"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";

const BreadcrumbOverrideContext = createContext<Map<string, string>>(new Map());

export function useBreadcrumbOverrides(): Map<string, string> {
  return useContext(BreadcrumbOverrideContext);
}

export function BreadcrumbOverride({
  segment,
  label,
  children,
}: {
  segment: string;
  label: string;
  children: ReactNode;
}) {
  const parent = useContext(BreadcrumbOverrideContext);
  const merged = useMemo(() => {
    const map = new Map(parent);
    map.set(segment, label);
    return map;
  }, [parent, segment, label]);
  return (
    <BreadcrumbOverrideContext value={merged}>
      {children}
    </BreadcrumbOverrideContext>
  );
}
