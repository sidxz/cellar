"use client";

import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/shared/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { useAppConfig } from "@/shared/lib/app-config";
import { cn } from "@/shared/lib/utils";
import { Check, ChevronsUpDown, ExternalLink, Plus, X } from "lucide-react";
import { useState } from "react";
import { useTargets } from "../hooks/use-targets";
import { TARGET_TYPE_LABELS, type Target, type TargetType } from "../types";
import { RequestTargetDialog } from "./request-target-dialog";

interface TargetMultiSelectProps {
  /** Currently-selected target ids. */
  value: string[];
  onChange: (ids: string[]) => void;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
}

function typeLabel(t: Target): string {
  return TARGET_TYPE_LABELS[t.target_type as TargetType] ?? t.target_type;
}

/**
 * Multi-select picker for biological targets — built on the same Command +
 * Popover primitives as `SearchableSelect`, but selecting many. Selected
 * targets render below as removable chips. "Request a new target" creates a
 * missing one in ProtCellar and selects it; "Manage in Prot-Cellar" opens the
 * catalog owner in a new tab. No UUID entry.
 */
export function TargetMultiSelect({
  value,
  onChange,
  disabled,
  placeholder = "Select targets…",
  className,
}: TargetMultiSelectProps) {
  const { data: targets } = useTargets();
  const { protCellarUrl } = useAppConfig();
  const [open, setOpen] = useState(false);
  const [requesting, setRequesting] = useState(false);

  const byId = new Map((targets ?? []).map((t) => [t.id, t] as const));
  const selected = value.map((id) => byId.get(id)).filter((t): t is Target => Boolean(t));

  const toggle = (id: string) => {
    // Guard the in-popover items too: the popover stays open across selects,
    // so without this a click during an in-flight mutation diffs against a
    // stale `value` and the gesture is silently swallowed.
    if (disabled) return;
    onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id]);
  };

  return (
    <div className={cn("space-y-2", className)}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            role="combobox"
            aria-expanded={open}
            disabled={disabled}
            className={cn(
              "w-full justify-between font-normal",
              selected.length === 0 && "text-muted-foreground",
            )}
          >
            {selected.length > 0
              ? `${selected.length} target${selected.length === 1 ? "" : "s"} selected`
              : placeholder}
            <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent
          className="w-[max(16rem,var(--radix-popover-trigger-width))] p-0"
          align="start"
        >
          <Command>
            <CommandInput placeholder="Search targets…" />
            <CommandList>
              <CommandEmpty>No targets found.</CommandEmpty>
              <CommandGroup>
                {(targets ?? []).map((t) => (
                  <CommandItem
                    key={t.id}
                    // Unique per target: same-named targets in different organisms must not collide.
                    value={`${t.name} ${t.organism ?? ""} ${t.id}`}
                    onSelect={() => toggle(t.id)}
                  >
                    <Check
                      className={cn(
                        "mr-2 h-4 w-4",
                        value.includes(t.id) ? "opacity-100" : "opacity-0",
                      )}
                    />
                    <span className="flex-1 truncate">
                      {t.name}
                      {t.organism && (
                        <span className="ml-2 text-muted-foreground text-xs">{t.organism}</span>
                      )}
                    </span>
                    <span className="ml-2 shrink-0 text-muted-foreground text-xs">
                      {typeLabel(t)}
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
              <CommandSeparator />
              <CommandGroup>
                <CommandItem
                  value="__request_target__"
                  // Kept while searching: a search that finds nothing is when it's needed.
                  forceMount
                  onSelect={() => {
                    setOpen(false);
                    setRequesting(true);
                  }}
                >
                  <Plus className="mr-2 h-4 w-4" />
                  Request a new target
                </CommandItem>
                <CommandItem
                  value="__manage_targets__"
                  onSelect={() => {
                    setOpen(false);
                    window.open(`${protCellarUrl}/targets`, "_blank", "noopener,noreferrer");
                  }}
                >
                  <ExternalLink className="mr-2 h-4 w-4" />
                  Manage in Prot-Cellar
                </CommandItem>
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>

      {/* Mounted only while open: the dialog owns the mutation and its form state. */}
      {requesting && (
        <RequestTargetDialog
          open
          onOpenChange={setRequesting}
          onCreated={(t) => {
            setRequesting(false);
            if (!value.includes(t.id)) onChange([...value, t.id]);
          }}
        />
      )}

      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {selected.map((t) => (
            <Badge key={t.id} variant="secondary" className="gap-1 font-normal">
              {t.name}
              {!disabled && (
                <button
                  type="button"
                  aria-label={`Remove ${t.name}`}
                  onClick={() => toggle(t.id)}
                  className="-mr-0.5 ml-0.5 rounded-sm opacity-60 hover:opacity-100"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}
