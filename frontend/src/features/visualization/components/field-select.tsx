"use client";

import type { SearchableSelectOption } from "@/shared/components/searchable-select";
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
import { Check, ChevronsUpDown } from "lucide-react";
import { useState } from "react";
import { fieldName, rankFields } from "../lib/field-search";
import { shortName } from "../lib/short-name";
import type { Dataset, DatasetColumn } from "../types";

/** A searchable picker of the dataset's visible columns of ``kinds``, grouped by readout
 * (each readout's layers under it; conditions and well details in their own groups). A
 * search lists the matches best first across groups (exact, then prefix, word, inside a
 * word, letters in order). The chosen field shows by its own name, its protocol under it. */
export function FieldSelect({
  ds,
  kinds,
  value,
  onChange,
  id,
  clearable = false,
  placeholder = "None",
  disabledReason,
  include,
  leading = [],
}: {
  ds: Dataset;
  kinds: DatasetColumn["kind"][];
  value: string | undefined;
  onChange: (key: string | undefined) => void;
  id?: string;
  /** Offer "None" (for optional settings such as color or split). */
  clearable?: boolean;
  placeholder?: string;
  /** Why a field cannot be chosen here, if it cannot (it stays listed, disabled). */
  disabledReason?: (c: DatasetColumn) => string | undefined;
  /** Keys offered whatever their kind (scatter X takes Run date). */
  include?: string[];
  /** Entries listed before the fields (the filter rail's "Substructure…"). */
  leading?: SearchableSelectOption[];
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const fields = ds.columns
    .filter((c) => !c.hidden && (kinds.includes(c.kind) || include?.includes(c.key)))
    .map((c) => ({
      value: c.key,
      label: c.label,
      group: c.group ?? "Details",
      disabledReason: disabledReason?.(c),
    }));
  const options: SearchableSelectOption[] = [...leading, ...fields];
  const selected = options.find((o) => o.value === value);
  const shown = selected && fieldName(selected);
  const searching = query.trim() !== "";
  // Searching: one list, best match first. Else: by group, in the dataset's order.
  const groups = new Map<string, SearchableSelectOption[]>();
  for (const o of rankFields(options, query)) {
    const heading = searching ? "" : (o.group ?? "");
    groups.set(heading, [...(groups.get(heading) ?? []), o]);
  }
  // Closing from here bypasses onOpenChange, so the search is cleared here too.
  const pick = (key: string | undefined) => {
    onChange(key);
    setOpen(false);
    setQuery("");
  };

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setQuery("");
      }}
    >
      <PopoverTrigger asChild>
        <Button
          id={id}
          variant="outline"
          role="combobox"
          aria-expanded={open}
          title={selected?.label}
          className={cn(
            "h-auto min-h-8 w-full min-w-0 justify-between px-2 py-1 text-sm font-normal",
            !shown && "text-muted-foreground",
          )}
        >
          <span className="flex min-w-0 flex-col items-start text-left leading-tight">
            <span className="w-full truncate">{shown?.name ?? placeholder}</span>
            {shown?.from && (
              <span className="w-full truncate text-xs text-muted-foreground">
                {shortName(shown.from)}
              </span>
            )}
          </span>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        className="w-[max(16rem,var(--radix-popover-trigger-width))] p-0"
        align="start"
      >
        <Command shouldFilter={false}>
          <CommandInput placeholder="Search fields…" value={query} onValueChange={setQuery} />
          <CommandList>
            <CommandEmpty>No matching field.</CommandEmpty>
            {clearable && value && !searching && (
              <CommandGroup>
                <CommandItem value="__clear__" onSelect={() => pick(undefined)}>
                  <span className="text-muted-foreground">None</span>
                </CommandItem>
              </CommandGroup>
            )}
            {[...groups].map(([heading, group]) => (
              <CommandGroup key={heading} heading={heading || undefined}>
                {group.map((o) => {
                  // A search's single list names each field's group unless its label does.
                  const from = searching && o.group && !o.label.startsWith(o.group) ? o.group : "";
                  const note = o.disabledReason ?? from;
                  return (
                    <CommandItem
                      key={o.value}
                      value={o.value}
                      disabled={Boolean(o.disabledReason)}
                      onSelect={() => pick(o.value)}
                    >
                      <Check
                        className={cn(
                          "mr-2 h-4 w-4 shrink-0",
                          value === o.value ? "opacity-100" : "opacity-0",
                        )}
                      />
                      {note ? (
                        <span className="flex flex-col">
                          {o.label}
                          <span className="text-xs text-muted-foreground">{note}</span>
                        </span>
                      ) : (
                        o.label
                      )}
                    </CommandItem>
                  );
                })}
              </CommandGroup>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
