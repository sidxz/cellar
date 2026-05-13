"use client";

import { useEffect, useState } from "react";

function readHash(): string {
  if (typeof window === "undefined") return "";
  return window.location.hash.replace(/^#/, "");
}

export function useHashTab(defaultTab: string): [string, (tab: string) => void] {
  const [tab, setTabState] = useState<string>(() => readHash() || defaultTab);

  useEffect(() => {
    setTabState((prev) => {
      const next = readHash() || defaultTab;
      return prev === next ? prev : next;
    });
    const onHashChange = () => {
      const next = readHash() || defaultTab;
      setTabState((prev) => (prev === next ? prev : next));
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, [defaultTab]);

  const setTab = (next: string) => {
    setTabState(next);
    if (typeof window !== "undefined") {
      const url =
        next === defaultTab
          ? window.location.pathname + window.location.search
          : `${window.location.pathname}${window.location.search}#${next}`;
      window.history.replaceState(null, "", url);
    }
  };

  return [tab, setTab];
}
