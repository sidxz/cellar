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
import { cn } from "@/shared/lib/utils";
import { Check, ChevronsUpDown } from "lucide-react";
import { useState } from "react";

export interface SearchableSelectOption {
  value: string;
  label: string;
  /** Heading the option is listed under; groups appear in first-seen order. */
  group?: string;
  /** Shown under the label of an option that cannot be chosen, saying why. */
  disabledReason?: string;
}

interface SearchableSelectProps {
  options: SearchableSelectOption[];
  value: string | null;
  onValueChange: (value: string | null) => void;
  placeholder?: string;
  searchPlaceholder?: string;
  emptyMessage?: string;
  className?: string;
  /** Id of the trigger, so a `<Label htmlFor>` names the combobox. */
  id?: string;
  /** Offer a "None" entry that clears the value (default true). */
  clearable?: boolean;
}

export function SearchableSelect({
  options,
  value,
  onValueChange,
  placeholder = "Select...",
  searchPlaceholder = "Search...",
  emptyMessage = "No results found.",
  className,
  id,
  clearable = true,
}: SearchableSelectProps) {
  const [open, setOpen] = useState(false);
  const selectedLabel = options.find((o) => o.value === value)?.label;
  const groups = new Map<string, SearchableSelectOption[]>();
  for (const o of options) {
    const list = groups.get(o.group ?? "");
    if (list) list.push(o);
    else groups.set(o.group ?? "", [o]);
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className={cn(
            "w-full justify-between font-normal",
            !selectedLabel && "text-muted-foreground",
            className,
          )}
        >
          <span className="truncate">{selectedLabel ?? placeholder}</span>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        className="w-[max(16rem,var(--radix-popover-trigger-width))] p-0"
        align="start"
      >
        <Command>
          <CommandInput placeholder={searchPlaceholder} />
          <CommandList>
            <CommandEmpty>{emptyMessage}</CommandEmpty>
            {clearable && value && (
              <CommandGroup>
                <CommandItem
                  value="__clear__"
                  onSelect={() => {
                    onValueChange(null);
                    setOpen(false);
                  }}
                >
                  <span className="text-muted-foreground">None</span>
                </CommandItem>
              </CommandGroup>
            )}
            {[...groups].map(([heading, group]) => (
              <CommandGroup key={heading} heading={heading || undefined}>
                {group.map((option) => (
                  <CommandItem
                    key={option.value}
                    value={option.label}
                    disabled={Boolean(option.disabledReason)}
                    onSelect={() => {
                      onValueChange(option.value);
                      setOpen(false);
                    }}
                  >
                    <Check
                      className={cn(
                        "mr-2 h-4 w-4",
                        value === option.value ? "opacity-100" : "opacity-0",
                      )}
                    />
                    {option.disabledReason ? (
                      <span className="flex flex-col">
                        {option.label}
                        <span className="text-xs text-muted-foreground">
                          {option.disabledReason}
                        </span>
                      </span>
                    ) : (
                      option.label
                    )}
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
