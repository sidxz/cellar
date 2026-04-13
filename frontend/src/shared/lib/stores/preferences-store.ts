"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface UserPreferences {
  theme: "light" | "dark" | "system";
  sidebarCollapsed: boolean;
  defaultSearchColumns: string[] | null;
}

interface PreferencesState extends UserPreferences {
  setTheme: (theme: UserPreferences["theme"]) => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setDefaultSearchColumns: (columns: string[] | null) => void;
  hydrate: (prefs: Partial<UserPreferences>) => void;
}

export const usePreferencesStore = create<PreferencesState>()(
  persist(
    (set) => ({
      theme: "dark",
      sidebarCollapsed: false,
      defaultSearchColumns: null,

      setTheme: (theme) => set({ theme }),
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      setDefaultSearchColumns: (defaultSearchColumns) => set({ defaultSearchColumns }),
      hydrate: (prefs) => set(prefs),
    }),
    { name: "cv-preferences" },
  ),
);
