"use client";
import { Button } from "@/shared/components/ui/button";
import { useFontFamilyStore } from "@/shared/stores/font-family-store";

export function FontToggle() {
  const font = useFontFamilyStore((s) => s.font);
  const setFont = useFontFamilyStore((s) => s.setFont);
  return (
    <div className="flex gap-1">
      <Button
        size="sm"
        variant={font === "plex" ? "default" : "outline"}
        aria-pressed={font === "plex"}
        onClick={() => setFont("plex")}
      >
        IBM Plex
      </Button>
      <Button
        size="sm"
        variant={font === "inter" ? "default" : "outline"}
        aria-pressed={font === "inter"}
        onClick={() => setFont("inter")}
      >
        Inter
      </Button>
    </div>
  );
}
