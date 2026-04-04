"use client";

import { Button } from "@/shared/components/ui/button";
import { usePreferencesStore } from "@/shared/lib/stores/preferences-store";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

export function ThemeToggle() {
  const { resolvedTheme, setTheme: setNextTheme } = useTheme();
  const setStoreTheme = usePreferencesStore((s) => s.setTheme);

  const toggle = () => {
    const next = resolvedTheme === "dark" ? "light" : "dark";
    setNextTheme(next);
    setStoreTheme(next);
  };

  return (
    <Button variant="ghost" size="icon" className="h-8 w-8" onClick={toggle}>
      <Sun className="size-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
      <Moon className="absolute size-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
      <span className="sr-only">Toggle theme</span>
    </Button>
  );
}
