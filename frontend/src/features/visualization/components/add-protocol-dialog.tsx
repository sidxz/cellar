"use client";

import { useProtocolSummaries } from "@/features/screening-assay/hooks/use-protocols";
import { StatusBadge } from "@/shared/components/status-badge";
import {
  Command,
  CommandEmpty,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/shared/components/ui/command";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { type RefObject, useState } from "react";
import type { ComparedProtocol } from "../types";
import { RunPickerDialog } from "./run-picker-dialog";

/** Pick a protocol by name (protocols in ``exclude`` are not offered), then its runs.
 * Closing gives focus to ``returnFocus`` (the run picker it swaps to never saw the opener). */
export function AddProtocolDialog({
  open,
  onOpenChange,
  exclude,
  onAdd,
  returnFocus,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  exclude: string[];
  onAdd: (p: ComparedProtocol) => void;
  returnFocus?: RefObject<HTMLElement | null>;
}) {
  const { data: protocols, isLoading } = useProtocolSummaries(undefined, { includeAll: true });
  const [picked, setPicked] = useState<string | null>(null);
  const onCloseAutoFocus = (e: Event) => {
    if (!returnFocus?.current) return;
    e.preventDefault();
    returnFocus.current.focus();
  };

  if (picked) {
    return (
      <RunPickerDialog
        protocolId={picked}
        level="compounds"
        confirmLabel="Add protocol"
        open={open}
        onOpenChange={onOpenChange}
        onConfirm={(runIds) => onAdd({ protocolId: picked, ...(runIds && { runIds }) })}
        onCloseAutoFocus={onCloseAutoFocus}
      />
    );
  }
  const shown = (protocols ?? []).filter((p) => !exclude.includes(p.id));
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" onCloseAutoFocus={onCloseAutoFocus}>
        <DialogHeader>
          <DialogTitle>Add a protocol</DialogTitle>
          <DialogDescription>
            Adds columns for the selected protocol and matches results by compound.
          </DialogDescription>
        </DialogHeader>
        <Command className="rounded-md border">
          <CommandInput placeholder="Search protocols…" />
          <CommandList>
            <CommandEmpty>{isLoading ? "Loading protocols…" : "No protocols found."}</CommandEmpty>
            {shown.map((p) => {
              const runs = p.run_count ?? 0;
              return (
                <CommandItem
                  key={p.id}
                  value={p.id}
                  keywords={[p.name, p.code ?? ""]}
                  disabled={runs === 0}
                  onSelect={() => setPicked(p.id)}
                >
                  <span className="min-w-0 flex-1 truncate">{p.name}</span>
                  <StatusBadge status={p.status} />
                  <span className="w-16 text-right text-xs text-muted-foreground tabular-nums">
                    {runs === 0 ? "No runs" : `${runs} ${runs === 1 ? "run" : "runs"}`}
                  </span>
                </CommandItem>
              );
            })}
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
