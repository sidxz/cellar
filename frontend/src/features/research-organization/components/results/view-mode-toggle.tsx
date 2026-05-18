"use client";

import { GitFork, LayoutGrid, Table } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { cn } from "@/shared/lib/utils";
import type { ViewMode } from "../../lib/use-view-mode";

export interface ViewModeToggleProps {
  mode: ViewMode;
  onChange: (mode: ViewMode) => void;
  className?: string;
}

export function ViewModeToggle({ mode, onChange, className }: ViewModeToggleProps) {
  return (
    <div
      className={cn("inline-flex items-center gap-1 rounded-md border border-input p-0.5", className)}
      role="group"
    >
      <Button
        type="button"
        variant={mode === "table" ? "default" : "ghost"}
        size="sm"
        className="h-7 px-2"
        aria-label="Table view"
        aria-pressed={mode === "table"}
        onClick={() => mode !== "table" && onChange("table")}
      >
        <Table className="h-3.5 w-3.5" />
      </Button>
      <Button
        type="button"
        variant={mode === "cards" ? "default" : "ghost"}
        size="sm"
        className="h-7 px-2"
        aria-label="Card view"
        aria-pressed={mode === "cards"}
        onClick={() => mode !== "cards" && onChange("cards")}
      >
        <LayoutGrid className="h-3.5 w-3.5" />
      </Button>
      <Button
        type="button"
        variant={mode === "scaffold-tree" ? "default" : "ghost"}
        size="sm"
        className="h-7 px-2"
        aria-label="Tree view"
        aria-pressed={mode === "scaffold-tree"}
        onClick={() => mode !== "scaffold-tree" && onChange("scaffold-tree")}
      >
        <GitFork className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}
