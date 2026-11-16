"use client";

import { useProjects } from "@/features/research-organization/hooks/use-projects";
import { Button } from "@/shared/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu";
import { ChartScatter, ChevronDown } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useSavedViews } from "../hooks/use-saved-views";
import { visualizeHref } from "../lib/source-url";
import { RunPickerDialog } from "./run-picker-dialog";

/** "Visualize" in a protocol or run header: a run opens the workbench directly; a
 * protocol asks which runs to load first, and its chevron lists the protocol's saved views. */
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
    <div className="inline-flex">
      <Button
        size="sm"
        variant="outline"
        className="rounded-r-none border-r-0"
        onClick={() => setOpen(true)}
      >
        <ChartScatter className="mr-2 h-4 w-4" />
        Visualize
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            size="sm"
            variant="outline"
            className="rounded-l-none px-2"
            aria-label="Saved views"
          >
            <ChevronDown className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-72">
          <DropdownMenuLabel>Saved views</DropdownMenuLabel>
          {/* Mounted with the open menu, so the protocol page lists views only when asked. */}
          <SavedViewItems protocolId={protocolId} />
        </DropdownMenuContent>
      </DropdownMenu>
      {/* Mounted only while open, so a protocol page never fetches row counts it won't show. */}
      {open && <RunPickerDialog protocolId={protocolId} open onOpenChange={setOpen} />}
    </div>
  );
}

function SavedViewItems({ protocolId }: { protocolId: string }) {
  const { data: views, isLoading, isError } = useSavedViews(protocolId);
  const { data: projects } = useProjects();
  const note = isLoading
    ? "Loading…"
    : isError
      ? "Couldn't load the saved views"
      : !views?.length
        ? "No saved views for this protocol yet"
        : null;
  if (note) return <p className="px-2 py-1.5 text-sm text-muted-foreground">{note}</p>;
  return views?.map((v) => (
    <DropdownMenuItem key={v.id} asChild>
      <Link href={`/assays/visualize/${v.id}`} className="flex items-center gap-2">
        <span className="min-w-0 flex-1 truncate">{v.name}</span>
        <span className="shrink-0 text-xs text-muted-foreground">
          {v.visibility === "private"
            ? "Private"
            : (projects?.find((p) => p.id === v.project_id)?.name ?? "Project")}
        </span>
      </Link>
    </DropdownMenuItem>
  ));
}
