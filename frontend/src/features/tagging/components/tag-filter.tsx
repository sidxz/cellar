"use client";

import { TagChip } from "@/shared/components/tag-chip";
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
import { cn } from "@/shared/lib/utils";
import { Check, Tag as TagIcon } from "lucide-react";
import { useState } from "react";
import { useTags } from "../hooks/use-tags";

export interface TagFilterValue {
  tagIds: string[];
  tagLogic: "any" | "all";
}

interface TagFilterProps {
  value: TagFilterValue;
  onChange: (v: TagFilterValue) => void;
}

export function TagFilter({ value, onChange }: TagFilterProps) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const debouncedQ = useDebounce(q, 200);
  const { data: tags } = useTags({ q: debouncedQ || undefined, limit: 50 });

  const toggle = (id: string) =>
    onChange({
      ...value,
      tagIds: value.tagIds.includes(id)
        ? value.tagIds.filter((x) => x !== id)
        : [...value.tagIds, id],
    });

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant={value.tagIds.length ? "secondary" : "outline"} size="sm">
          <TagIcon className="mr-2 h-4 w-4" />
          Tags{value.tagIds.length ? ` (${value.tagIds.length})` : ""}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput
            value={q}
            onValueChange={setQ}
            placeholder="Search tags…"
            className="h-8 text-sm"
          />
          <CommandList>
            <CommandEmpty className="px-3 py-2 text-xs text-muted-foreground">
              No tags.
            </CommandEmpty>
            <CommandGroup>
              {tags?.map((t) => (
                <CommandItem
                  key={t.id}
                  value={`${t.key}=${t.value ?? ""}`}
                  onSelect={() => toggle(t.id)}
                  className="gap-1.5 text-sm"
                >
                  <Check
                    className={cn(
                      "h-3 w-3",
                      value.tagIds.includes(t.id) ? "opacity-100" : "opacity-0",
                    )}
                  />
                  <TagChip tagKey={t.key} value={t.value} />
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
          {value.tagIds.length > 1 && (
            <div className="flex items-center justify-between border-t border-border px-3 py-2 text-xs">
              <span className="text-muted-foreground">Match</span>
              <div className="flex gap-1">
                {(["any", "all"] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => onChange({ ...value, tagLogic: mode })}
                    className={cn(
                      "rounded px-2 py-0.5 capitalize",
                      value.tagLogic === mode
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
          {value.tagIds.length > 0 && (
            <button
              type="button"
              onClick={() => onChange({ tagIds: [], tagLogic: value.tagLogic })}
              className="w-full border-t border-border px-3 py-1.5 text-left text-xs text-muted-foreground hover:bg-accent"
            >
              Clear tag filter
            </button>
          )}
        </Command>
      </PopoverContent>
    </Popover>
  );
}
