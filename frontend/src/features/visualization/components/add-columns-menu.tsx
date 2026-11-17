"use client";

import { Button } from "@/shared/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu";
import { Columns3 } from "lucide-react";
import { useState } from "react";
import type { DerivedSpec } from "../lib/derived";

const KINDS = [
  { kind: "rgroups", label: "R-groups…" },
  { kind: "clusters", label: "Clusters…" },
  { kind: "series", label: "Series…" },
] satisfies { kind: DerivedSpec["kind"]; label: string }[];

/** "Add columns": the chemistry column sets (quieter than Add plot); disabled, with the
 * reason on hover, when ``disabledReason`` is set. */
export function AddColumnsMenu({
  onPick,
  disabledReason,
}: {
  onPick: (kind: DerivedSpec["kind"]) => void;
  disabledReason?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    // Unavailable yet focusable, so the title says why to keyboard users too.
    <DropdownMenu open={open} onOpenChange={(o) => setOpen(o && !disabledReason)}>
      <DropdownMenuTrigger asChild>
        <Button
          size="sm"
          variant="ghost"
          className="h-8"
          aria-disabled={Boolean(disabledReason)}
          title={disabledReason}
        >
          <Columns3 className="h-4 w-4" />
          Add columns
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {KINDS.map(({ kind, label }) => (
          <DropdownMenuItem key={kind} onSelect={() => onPick(kind)}>
            {label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
