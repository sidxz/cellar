"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface UserPreferences {
  theme: "light" | "dark" | "system";
  sidebarCollapsed: boolean;
}

interface PreferencesState extends UserPreferences {
  setTheme: (theme: UserPreferences["theme"]) => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  hydrate: (prefs: Partial<UserPreferences>) => void;
}

export const usePreferencesStore = create<PreferencesState>()(
  persist(
    (set) => ({
      theme: "dark",
      sidebarCollapsed: false,

      setTheme: (theme) => set({ theme }),
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      hydrate: (prefs) => set(prefs),
    }),
    { name: "cv-preferences" },
  ),
);
