"use client";

import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { cn } from "@/shared/lib/utils";
import { Plus, Trash2 } from "lucide-react";
import { useRef } from "react";
import { PICK_LIST_COLORS, resolvePickListColor } from "../lib/pick-list-colors";
import type { PickListValue } from "../types";

interface PickListEditorProps {
  value: PickListValue[];
  onChange: (next: PickListValue[]) => void;
  disabled?: boolean;
  className?: string;
}

/** Per-row editor: label input + color swatch button + delete.
 *
 *  Color is optional — clicking the swatch opens a small palette popover
 *  with 8 preset colors plus an "Auto" entry that clears `color` so the
 *  badge falls back to the hash-derived stable color. We deliberately do
 *  NOT expose a free hex picker; the palette keeps the app's badge
 *  vocabulary consistent across protocols.
 */
export function PickListEditor({
  value,
  onChange,
  disabled = false,
  className,
}: PickListEditorProps) {
  // Stable per-row keys so middle-deletes don't shift focus / popover state
  // onto a different row. Resized in lockstep with the value array.
  const keysRef = useRef<string[]>([]);
  while (keysRef.current.length < value.length) {
    keysRef.current.push(
      `${Date.now()}-${keysRef.current.length}-${Math.random().toString(36).slice(2, 8)}`,
    );
  }
  if (keysRef.current.length > value.length) {
    keysRef.current = keysRef.current.slice(0, value.length);
  }

  const updateAt = (i: number, patch: Partial<PickListValue>) => {
    const next = value.slice();
    next[i] = { ...next[i], ...patch };
    onChange(next);
  };
  const removeAt = (i: number) => {
    keysRef.current = keysRef.current.filter((_, j) => j !== i);
    onChange(value.filter((_, j) => j !== i));
  };
  const append = () => {
    onChange([...value, { label: "", color: null }]);
  };

  return (
    <div className={cn("space-y-2", className)}>
      {value.length === 0 && (
        <p className="text-xs text-muted-foreground italic">
          No values yet. Add at least one for the readout to be valid.
        </p>
      )}
      {value.map((v, i) => {
        const resolved = resolvePickListColor(v.label || "—", v.color);
        return (
          <div key={keysRef.current[i]} className="flex items-center gap-2">
            <Input
              value={v.label}
              onChange={(e) => updateAt(i, { label: e.target.value })}
              placeholder="Value label (e.g. Active)"
              disabled={disabled}
              className="flex-1"
            />
            <Popover>
              <PopoverTrigger asChild>
                <button
                  type="button"
                  disabled={disabled}
                  title={
                    v.color
                      ? `Color: ${resolved.name}`
                      : `Auto color: ${resolved.name} (click to override)`
                  }
                  className={cn(
                    "h-9 w-9 rounded-md border-2 transition-colors",
                    "flex items-center justify-center",
                    v.color ? "border-foreground/40" : "border-dashed border-muted-foreground/40",
                    "hover:border-foreground",
                    disabled && "cursor-not-allowed opacity-50",
                  )}
                >
                  <span className={cn("h-4 w-4 rounded-full", resolved.dot)} />
                </button>
              </PopoverTrigger>
              <PopoverContent align="end" className="w-auto p-2" sideOffset={4}>
                <div className="grid grid-cols-4 gap-2">
                  {PICK_LIST_COLORS.map((c) => (
                    <button
                      key={c.hex}
                      type="button"
                      onClick={() => updateAt(i, { color: c.hex })}
                      title={c.name}
                      className={cn(
                        "h-7 w-7 rounded-md border-2 transition-all",
                        c.dot,
                        v.color === c.hex
                          ? "border-foreground scale-110"
                          : "border-transparent hover:border-foreground/40",
                      )}
                    />
                  ))}
                </div>
                <button
                  type="button"
                  onClick={() => updateAt(i, { color: null })}
                  className={cn(
                    "mt-2 w-full rounded-md border px-2 py-1 text-xs",
                    "text-muted-foreground hover:bg-accent",
                    !v.color && "border-foreground bg-accent",
                  )}
                >
                  Auto (hash from label)
                </button>
              </PopoverContent>
            </Popover>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-9 w-9 text-destructive hover:text-destructive"
              onClick={() => removeAt(i)}
              disabled={disabled}
              title="Remove value"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        );
      })}
      <Button type="button" variant="outline" size="sm" onClick={append} disabled={disabled}>
        <Plus className="mr-1 h-3.5 w-3.5" /> Add value
      </Button>
    </div>
  );
}
