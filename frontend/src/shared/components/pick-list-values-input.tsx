"use client";

import { Input } from "@/shared/components/ui/input";
import { X } from "lucide-react";
import { useState } from "react";

/** Appends a trimmed value; blanks and case-insensitive duplicates are ignored. */
export function addPickListValue(values: string[], raw: string): string[] {
  const v = raw.trim();
  if (!v || values.some((x) => x.toLowerCase() === v.toLowerCase())) return values;
  return [...values, v];
}

interface Props {
  values: string[];
  onChange: (values: string[]) => void;
}

/** Chips editor for a pick list's allowed values: Enter (or leaving the box) adds, the x removes. */
export function PickListValuesInput({ values, onChange }: Props) {
  const [draft, setDraft] = useState("");
  const commit = () => {
    onChange(addPickListValue(values, draft));
    setDraft("");
  };
  return (
    <div className="grid gap-1.5">
      {values.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {values.map((v) => (
            <span
              key={v}
              className="inline-flex items-center gap-1 rounded-full border bg-muted px-2 py-0.5 text-xs"
            >
              {v}
              <button
                type="button"
                aria-label={`Remove ${v}`}
                className="text-muted-foreground hover:text-foreground"
                onClick={() => onChange(values.filter((x) => x !== v))}
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}
      <Input
        value={draft}
        placeholder="Type a value, press Enter"
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key !== "Enter") return;
          e.preventDefault();
          commit();
        }}
        onBlur={commit}
      />
      {values.length === 0 && <p className="text-xs text-destructive">Add at least one value.</p>}
    </div>
  );
}
