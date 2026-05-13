"use client";

import { Input } from "@/shared/components/ui/input";
import { cn } from "@/shared/lib/utils";
import { type KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  type FormulaSuggestion,
  buildSuggestions,
  tokenAtCursor,
  validateFormula,
} from "../lib/formula-tokens";

/** Rich formula input for calculated readouts.
 *
 *  Wraps a plain text Input with:
 *    - Cursor-aware autocomplete popover. As you type:
 *      • a normal identifier (e.g. `Ra`) → suggests current protocol's
 *        readout names + math whitelist
 *      • `@` or `@Pro` → suggests workspace protocol names (cross-protocol
 *        references). Suggestions auto-append `.` so the user can keep typing.
 *      Keyboard nav: ↑/↓ to cycle, Enter or Tab to commit, Esc to dismiss.
 *    - Live validation line below the input. Tokenises the formula and
 *      flags identifiers that aren't readouts, math symbols, or
 *      cross-protocol refs. Doesn't block save — backend is authoritative.
 */
interface FormulaInputProps {
  value: string;
  onChange: (next: string) => void;
  /** Names of readouts available in the current protocol that this formula
   *  can reference. Should EXCLUDE the readout being edited (a readout
   *  can't reference itself) and any other calculated readouts that
   *  haven't been resolved yet (caller's call). */
  availableReadoutNames: readonly string[];
  /** Workspace protocol names for `@`-completion. Empty list disables that
   *  branch — the user can still type cross-protocol refs by hand. */
  protocolNames?: readonly string[];
  disabled?: boolean;
  placeholder?: string;
  className?: string;
}

export function FormulaInput({
  value,
  onChange,
  availableReadoutNames,
  protocolNames = [],
  disabled = false,
  placeholder = "e.g. 100 * (1 - Raw / Control)",
  className,
}: FormulaInputProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [cursorPos, setCursorPos] = useState(0);
  const [activeIdx, setActiveIdx] = useState(0);
  // Set to true after Esc; reset on next keystroke. Lets the user dismiss
  // the popover without losing their typing position.
  const [dismissed, setDismissed] = useState(false);

  const token = useMemo(() => tokenAtCursor(value, cursorPos), [value, cursorPos]);
  const suggestions = useMemo(
    () => buildSuggestions(token, availableReadoutNames, protocolNames),
    [token, availableReadoutNames, protocolNames],
  );
  const validation = useMemo(
    () => validateFormula(value, availableReadoutNames),
    [value, availableReadoutNames],
  );

  const showPopover = !disabled && !dismissed && suggestions.length > 0 && token.kind !== "none";

  // Reset active index whenever suggestions change so we don't point past
  // the end of the new list.
  useEffect(() => {
    setActiveIdx(0);
  }, [suggestions]);

  // Click-outside dismisses the popover.
  useEffect(() => {
    if (!showPopover) return;
    function onDoc(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setDismissed(true);
      }
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [showPopover]);

  /** Replace the token under the cursor with `text` and move cursor
   *  past the inserted text. In bracket mode, also consume an
   *  immediately-following `]` so the user isn't left with a dangling
   *  `]]` after their pre-typed closing bracket. */
  const commit = useCallback(
    (suggestion: FormulaSuggestion) => {
      const inserted = suggestion.value;
      const before = value.slice(0, token.start);
      let afterStart = cursorPos;
      if (token.kind === "bracket" && value[afterStart] === "]") {
        afterStart += 1;
      }
      const after = value.slice(afterStart);
      const next = before + inserted + after;
      onChange(next);

      // Position cursor at the end of the inserted text. We have to wait
      // a tick for the controlled value to land in the DOM before setting
      // the selection range.
      const newPos = token.start + inserted.length;
      requestAnimationFrame(() => {
        const el = inputRef.current;
        if (!el) return;
        el.focus();
        el.setSelectionRange(newPos, newPos);
        setCursorPos(newPos);
      });
    },
    [value, cursorPos, token.start, token.kind, onChange],
  );

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (!showPopover) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIdx((i) => (i + 1) % suggestions.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIdx((i) => (i - 1 + suggestions.length) % suggestions.length);
    } else if (e.key === "Enter" || e.key === "Tab") {
      e.preventDefault();
      commit(suggestions[activeIdx]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setDismissed(true);
    }
  };

  const handleSelect = (e: React.SyntheticEvent<HTMLInputElement>) => {
    setCursorPos(e.currentTarget.selectionStart ?? 0);
    setDismissed(false);
  };

  // ── validation line content ───────────────────────────────────────────
  let validationLine: React.ReactNode = null;
  if (!validation.empty) {
    if (validation.unknownIdentifiers.length > 0) {
      validationLine = (
        <p className="text-[11px] text-destructive">
          Unknown: <code className="font-mono">{validation.unknownIdentifiers.join(", ")}</code> —
          not a readout in this protocol or a math function.
        </p>
      );
    } else {
      const parts: string[] = [];
      if (validation.knownReadouts.length > 0) {
        parts.push(
          `${validation.knownReadouts.length} variable${
            validation.knownReadouts.length === 1 ? "" : "s"
          }: ${validation.knownReadouts.join(", ")}`,
        );
      }
      if (validation.hasCrossProtocolRefs) {
        parts.push("includes cross-protocol reference (resolved at read)");
      }
      validationLine = (
        <p className="text-[11px] text-muted-foreground">✓ {parts.join(" · ") || "valid syntax"}</p>
      );
    }
  }

  return (
    <div ref={containerRef} className={cn("relative space-y-1", className)}>
      <Input
        ref={inputRef}
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          // Set cursor position from the input AFTER React applies the
          // controlled value. Using onChange's currentTarget gives us the
          // post-edit position directly.
          setCursorPos(e.target.selectionStart ?? e.target.value.length);
          setDismissed(false);
        }}
        onSelect={handleSelect}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder={placeholder}
        className="font-mono text-sm"
        autoComplete="off"
        spellCheck={false}
      />
      {showPopover && (
        <div
          className={cn(
            "absolute z-50 left-0 top-full mt-1 max-h-64 w-full overflow-y-auto",
            "rounded-md border bg-popover text-popover-foreground shadow-lg",
          )}
        >
          <ul className="py-1">
            {suggestions.map((s, i) => (
              <li key={`${s.kind}-${s.value}`}>
                <button
                  type="button"
                  onMouseDown={(e) => {
                    // Prevent the input from blurring before our click
                    // handler runs.
                    e.preventDefault();
                    commit(s);
                  }}
                  onMouseEnter={() => setActiveIdx(i)}
                  className={cn(
                    "flex w-full items-center justify-between px-3 py-1.5 text-sm",
                    "font-mono",
                    i === activeIdx && "bg-accent",
                  )}
                >
                  <span>{s.value}</span>
                  {s.hint && (
                    <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                      {s.hint}
                    </span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {validationLine}
    </div>
  );
}
