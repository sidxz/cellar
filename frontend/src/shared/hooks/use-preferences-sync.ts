"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { type UserPreferences, usePreferencesStore } from "@/shared/lib/stores/preferences-store";
import { useAuthz } from "@sentinel-auth/nextjs";
import { useQuery } from "@tanstack/react-query";
import { useTheme } from "next-themes";
import { useEffect, useRef } from "react";

interface ServerPreferences {
  theme?: string;
  sidebar_collapsed?: boolean;
  default_search_columns?: string[] | null;
}

async function fetchPreferences(): Promise<ServerPreferences> {
  return customInstance<ServerPreferences>({
    url: `${API_V1}/user/preferences`,
    method: "GET",
  });
}

async function patchPreferences(prefs: ServerPreferences): Promise<void> {
  await customInstance<void>({
    url: `${API_V1}/user/preferences`,
    method: "PATCH",
    data: prefs,
  });
}

/**
 * Syncs user preferences between Zustand (localStorage), next-themes, and the backend.
 *
 * On login: fetches server prefs → hydrates Zustand store → updates next-themes.
 * On change: debounced PATCH to server (1s idle).
 * Gracefully falls back to localStorage if backend is unavailable.
 */
export function usePreferencesSync() {
  const { isAuthenticated } = useAuthz();
  const { setTheme: setNextTheme } = useTheme();
  const { theme, sidebarCollapsed, defaultSearchColumns, hydrate } = usePreferencesStore();

  const syncingRef = useRef(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hydratedRef = useRef(false);

  // Fetch server preferences once on login
  const { data: serverPrefs } = useQuery({
    queryKey: ["user", "preferences"],
    queryFn: fetchPreferences,
    enabled: isAuthenticated,
    staleTime: Number.POSITIVE_INFINITY,
    retry: 1,
  });

  // Hydrate stores from server (one-time after fetch)
  useEffect(() => {
    if (!serverPrefs || hydratedRef.current) return;
    hydratedRef.current = true;
    syncingRef.current = true;

    const prefs: Partial<UserPreferences> = {};
    if (serverPrefs.theme) prefs.theme = serverPrefs.theme as UserPreferences["theme"];
    if (serverPrefs.sidebar_collapsed !== undefined)
      prefs.sidebarCollapsed = serverPrefs.sidebar_collapsed;
    if (serverPrefs.default_search_columns !== undefined)
      prefs.defaultSearchColumns = serverPrefs.default_search_columns;

    hydrate(prefs);
    if (prefs.theme) setNextTheme(prefs.theme);

    // Allow sync after a tick
    requestAnimationFrame(() => {
      syncingRef.current = false;
    });
  }, [serverPrefs, hydrate, setNextTheme]);

  // Debounced sync to backend on store changes
  useEffect(() => {
    if (!isAuthenticated || syncingRef.current || !hydratedRef.current) return;

    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      patchPreferences({
        theme,
        sidebar_collapsed: sidebarCollapsed,
        default_search_columns: defaultSearchColumns,
      }).catch(() => {
        // Silent fail — localStorage is the fallback
      });
    }, 1000);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [isAuthenticated, theme, sidebarCollapsed, defaultSearchColumns]);
}
