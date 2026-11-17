"use client";

import { Button } from "@/shared/components/ui/button";
import { Checkbox } from "@/shared/components/ui/checkbox";
import { Label } from "@/shared/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { Columns3 } from "lucide-react";
import { useMemo, useState } from "react";

type Choices = Record<string, boolean>;

function read(key: string): Choices {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(key) ?? "{}");
    if (!value || typeof value !== "object" || Array.isArray(value)) return {};
    return Object.fromEntries(Object.entries(value).filter(([, v]) => typeof v === "boolean"));
  } catch {
    return {};
  }
}

export function useRunColumnChoices(protocolId: string) {
  const key = `cellar.runs.columns.${protocolId}`;
  const saved = useMemo(() => read(key), [key]);
  const [byKey, setByKey] = useState<Record<string, Choices>>({});
  const choices = byKey[key] ?? saved;
  const save = (next: Choices) => {
    setByKey((current) => ({ ...current, [key]: next }));
    try {
      localStorage.setItem(key, JSON.stringify(next));
    } catch {
      // Choices still apply for this visit when storage is unavailable.
    }
  };
  return {
    choices,
    toggle: (id: string, show: boolean) => save({ ...choices, [id]: show }),
    reset: () => save({}),
  };
}

export function RunColumnsMenu({
  columns,
  onToggle,
  onReset,
}: {
  columns: { id: string; label: string; visible: boolean; locked: boolean }[];
  onToggle: (id: string, show: boolean) => void;
  onReset: () => void;
}) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm">
          <Columns3 className="size-4" /> Columns
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="max-h-[60vh] w-72 space-y-3 overflow-y-auto">
        <p className="text-sm font-medium">Show columns</p>
        {columns.map((column) => (
          <div key={column.id} className="flex items-center gap-2">
            <Checkbox
              id={`run-column-${column.id}`}
              checked={column.visible}
              disabled={column.locked}
              onCheckedChange={(value) => onToggle(column.id, value === true)}
            />
            <Label htmlFor={`run-column-${column.id}`} className="font-normal">
              {column.label}
            </Label>
          </div>
        ))}
        <Button variant="ghost" size="sm" className="w-full" onClick={onReset}>
          Reset to defaults
        </Button>
      </PopoverContent>
    </Popover>
  );
}
