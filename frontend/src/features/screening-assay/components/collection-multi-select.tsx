"use client";

import { CollectionTypeIcon } from "@/features/research-organization/components/collection/collection-type-icon";
import { useCollections } from "@/features/research-organization/hooks/use-collections";
import { COLLECTION_TYPE_LABELS, type Collection } from "@/features/research-organization/types";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/shared/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { cn } from "@/shared/lib/utils";
import { Check, ChevronsUpDown, X } from "lucide-react";
import { useMemo, useState } from "react";

/**
 * Multi-select picker for collections — mirrors `TargetMultiSelect` but sources
 * from the workspace collections list (Library type sorted first, since that's
 * the screening-relevant set). Selected collections render below as removable
 * chips. No UUID entry.
 */
export function CollectionMultiSelect({
  value,
  onChange,
  disabled,
  placeholder = "Add a collection…",
  projectIds,
  className,
}: {
  value: string[];
  onChange: (ids: string[]) => void;
  disabled?: boolean;
  placeholder?: string;
  projectIds?: string[];
  className?: string;
}) {
  const { data: collections } = useCollections(projectIds, { includeAll: true });
  const [open, setOpen] = useState(false);

  const ordered = useMemo(() => {
    return [...(collections ?? [])].sort((a, b) => {
      const al = a.type === "library" ? 0 : 1;
      const bl = b.type === "library" ? 0 : 1;
      return al - bl || a.name.localeCompare(b.name);
    });
  }, [collections]);

  const byId = new Map((collections ?? []).map((c) => [c.id, c] as const));
  const selected = value.map((id) => byId.get(id)).filter((c): c is Collection => Boolean(c));

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
              ? `${selected.length} collection${selected.length === 1 ? "" : "s"} selected`
              : placeholder}
            <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
          <Command>
            <CommandInput placeholder="Search collections…" />
            <CommandList>
              <CommandEmpty>No collections found.</CommandEmpty>
              <CommandGroup>
                {ordered.map((c) => (
                  <CommandItem key={c.id} value={c.name} onSelect={() => toggle(c.id)}>
                    <Check
                      className={cn(
                        "mr-2 h-4 w-4",
                        value.includes(c.id) ? "opacity-100" : "opacity-0",
                      )}
                    />
                    <CollectionTypeIcon type={c.type} className="mr-1.5 shrink-0" />
                    <span className="flex-1 truncate">{c.name}</span>
                    <span className="ml-2 shrink-0 text-muted-foreground text-xs">
                      {COLLECTION_TYPE_LABELS[c.type]}
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>

      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {selected.map((c) => (
            <Badge key={c.id} variant="secondary" className="gap-1 font-normal">
              <CollectionTypeIcon type={c.type} />
              {c.name}
              {!disabled && (
                <button
                  type="button"
                  aria-label={`Remove ${c.name}`}
                  onClick={() => toggle(c.id)}
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
