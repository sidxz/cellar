"use client";

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
import { useDebounce } from "@/shared/hooks/use-debounce";
import { SEARCH_DEBOUNCE_MS } from "@/shared/lib/timing";
import { cn } from "@/shared/lib/utils";
import { Check, Target as TargetIcon } from "lucide-react";
import { useState } from "react";
import { useTargets } from "../hooks/use-targets";

export interface TargetFilterValue {
  targetIds: string[];
  targetLogic: "any" | "all";
}

interface TargetFilterProps {
  value: TargetFilterValue;
  onChange: (v: TargetFilterValue) => void;
}

export function TargetFilter({ value, onChange }: TargetFilterProps) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const debouncedQ = useDebounce(q, SEARCH_DEBOUNCE_MS);
  const params: Record<string, string> = { limit: "50" };
  if (debouncedQ) params.q = debouncedQ;
  const { data: targets } = useTargets(params);

  const toggle = (id: string) =>
    onChange({
      ...value,
      targetIds: value.targetIds.includes(id)
        ? value.targetIds.filter((x) => x !== id)
        : [...value.targetIds, id],
    });

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant={value.targetIds.length ? "secondary" : "outline"} size="sm">
          <TargetIcon className="mr-2 h-4 w-4" />
          Targets{value.targetIds.length ? ` (${value.targetIds.length})` : ""}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput
            value={q}
            onValueChange={setQ}
            placeholder="Search targets…"
            className="h-8 text-sm"
          />
          <CommandList>
            <CommandEmpty className="px-3 py-2 text-xs text-muted-foreground">
              No targets.
            </CommandEmpty>
            <CommandGroup>
              {targets?.map((t) => (
                <CommandItem
                  key={t.id}
                  value={t.name}
                  onSelect={() => toggle(t.id)}
                  className="gap-1.5 text-sm"
                >
                  <Check
                    className={cn(
                      "h-3 w-3",
                      value.targetIds.includes(t.id) ? "opacity-100" : "opacity-0",
                    )}
                  />
                  {t.name}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
          {value.targetIds.length > 1 && (
            <div className="flex items-center justify-between border-t border-border px-3 py-2 text-xs">
              <span className="text-muted-foreground">Match</span>
              <div className="flex gap-1">
                {(["any", "all"] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => onChange({ ...value, targetLogic: mode })}
                    className={cn(
                      "rounded px-2 py-0.5 capitalize",
                      value.targetLogic === mode
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:bg-accent",
                    )}
                  >
                    {mode}
                  </button>
                ))}
              </div>
            </div>
          )}
          {value.targetIds.length > 0 && (
            <button
              type="button"
              onClick={() => onChange({ targetIds: [], targetLogic: value.targetLogic })}
              className="w-full border-t border-border px-3 py-1.5 text-left text-xs text-muted-foreground hover:bg-accent"
            >
              Clear target filter
            </button>
          )}
        </Command>
      </PopoverContent>
    </Popover>
  );
}
