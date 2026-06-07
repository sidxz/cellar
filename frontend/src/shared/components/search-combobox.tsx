"use client";

import { Command, CommandEmpty, CommandItem, CommandList } from "@/shared/components/ui/command";
import { Input } from "@/shared/components/ui/input";
import { Popover, PopoverAnchor, PopoverContent } from "@/shared/components/ui/popover";
import { cn } from "@/shared/lib/utils";
import { X } from "lucide-react";
import { type ReactNode, type RefObject, useId, useRef } from "react";

export interface SearchComboboxProps<T> {
  /** Current text in the search box (controlled by the caller). */
  searchValue: string;
  /** Fired on every keystroke with the new search text. */
  onSearchChange: (value: string) => void;
  /** Already-filtered result rows from the caller's query hook. */
  items: T[];
  /** Stable key for a row (used as the React + cmdk item key). */
  getItemKey: (item: T) => string;
  /** Render the visible content of a result row. */
  renderItem: (item: T) => ReactNode;
  /** Called when the user picks a row (click or Enter on the highlighted row). */
  onSelect: (item: T) => void;
  /** True while the caller's query is in flight. */
  isLoading?: boolean;
  /**
   * Whether the dropdown should be shown. The caller owns this so it can gate
   * on a minimum query length, focus, selection state, etc. The popover also
   * dismisses on outside click / Escape via Radix regardless of this flag.
   */
  open: boolean;
  /** Notified when Radix wants to change open state (outside click, Escape). */
  onOpenChange: (open: boolean) => void;
  placeholder?: string;
  /** Shown (centered) when there are no items and not loading. */
  emptyMessage?: string;
  /** Shown (centered) while loading. */
  loadingMessage?: string;
  disabled?: boolean;
  /** Optional clear (X) affordance inside the input. Omit to hide it. */
  onClear?: () => void;
  clearAriaLabel?: string;
  autoFocus?: boolean;
  /** Forwarded to the underlying input (e.g. for Enter-to-submit shortcuts). */
  onInputKeyDown?: (e: React.KeyboardEvent<HTMLInputElement>) => void;
  /** Forwarded to the underlying input (e.g. to reopen the dropdown on focus). */
  onInputFocus?: (e: React.FocusEvent<HTMLInputElement>) => void;
  /** Extra content rendered below the result list (e.g. a free-text footer). */
  footer?: ReactNode;
  inputRef?: RefObject<HTMLInputElement | null>;
  className?: string;
  /** Tailwind classes for the input element. */
  inputClassName?: string;
}

/**
 * Debounced/async search dropdown built on shadcn Popover + Command.
 *
 * Replaces the hand-rolled "relative container + absolute z-50 results list +
 * mousedown click-outside effect + onMouseDown-preventDefault buttons" combobox
 * that was copy-pasted across the molecule / batch / member / ontology pickers.
 * Radix Popover supplies outside-dismiss and Escape; cmdk supplies arrow-key
 * navigation. The caller owns debounce + minimum-query gating (via `open`) and
 * supplies the already-filtered `items` — this component does no filtering of
 * its own (`shouldFilter={false}`), preserving the server-search semantics.
 *
 * Selection is always explicit: nothing is auto-selected on open or blur.
 */
export function SearchCombobox<T>({
  searchValue,
  onSearchChange,
  items,
  getItemKey,
  renderItem,
  onSelect,
  isLoading = false,
  open,
  onOpenChange,
  placeholder,
  emptyMessage = "No results found.",
  loadingMessage = "Searching...",
  disabled = false,
  onClear,
  clearAriaLabel = "Clear",
  autoFocus = false,
  onInputKeyDown,
  onInputFocus,
  footer,
  inputRef,
  className,
  inputClassName,
}: SearchComboboxProps<T>) {
  const internalInputRef = useRef<HTMLInputElement>(null);
  const resolvedInputRef = inputRef ?? internalInputRef;
  const listId = useId();

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverAnchor asChild>
        <div className={cn("relative", className)}>
          <Input
            ref={resolvedInputRef}
            value={searchValue}
            onChange={(e) => onSearchChange(e.target.value)}
            onKeyDown={onInputKeyDown}
            onFocus={onInputFocus}
            placeholder={placeholder}
            disabled={disabled}
            autoFocus={autoFocus}
            className={cn(onClear && "pr-8", inputClassName)}
            role="combobox"
            aria-expanded={open}
            aria-controls={listId}
            aria-autocomplete="list"
          />
          {onClear && (
            <button
              type="button"
              onClick={onClear}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-muted-foreground hover:text-foreground"
              aria-label={clearAriaLabel}
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </PopoverAnchor>
      <PopoverContent
        id={listId}
        className="w-[--radix-popover-trigger-width] p-0"
        align="start"
        // Keep focus in the input so the user can keep typing; cmdk still
        // tracks the highlighted item for arrow-key navigation.
        onOpenAutoFocus={(e) => e.preventDefault()}
      >
        <Command shouldFilter={false}>
          <CommandList>
            {isLoading ? (
              <div className="px-3 py-2 text-sm text-muted-foreground">{loadingMessage}</div>
            ) : items.length === 0 ? (
              <CommandEmpty>{emptyMessage}</CommandEmpty>
            ) : (
              items.map((item) => {
                const key = getItemKey(item);
                return (
                  <CommandItem
                    key={key}
                    value={key}
                    onSelect={() => onSelect(item)}
                    className="cursor-pointer"
                  >
                    {renderItem(item)}
                  </CommandItem>
                );
              })
            )}
            {footer}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
