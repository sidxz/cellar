"use client";

import { Button } from "@/shared/components/ui/button";
import { ChartScatter } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { visualizeHref } from "../lib/source-url";
import { RunPickerDialog } from "./run-picker-dialog";

/** "Visualize" in a protocol or run header: a run opens the workbench directly; a
 * protocol asks which runs to load first. */
export function VisualizeButton({ protocolId, runId }: { protocolId?: string; runId?: string }) {
  const [open, setOpen] = useState(false);
  if (runId) {
    return (
      <Button size="sm" variant="outline" asChild>
        <Link href={visualizeHref({ kind: "run", runId })}>
          <ChartScatter className="mr-2 h-4 w-4" />
          Visualize
        </Link>
      </Button>
    );
  }
  if (!protocolId) return null;
  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <ChartScatter className="mr-2 h-4 w-4" />
        Visualize
      </Button>
      {/* Mounted only while open, so a protocol page never fetches row counts it won't show. */}
      {open && <RunPickerDialog protocolId={protocolId} open onOpenChange={setOpen} />}
    </>
  );
}
