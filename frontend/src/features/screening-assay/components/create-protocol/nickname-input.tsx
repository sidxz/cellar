"use client";

import { Badge } from "@/shared/components/ui/badge";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { X } from "lucide-react";
import { useState } from "react";

/** Names people already use for this assay, added with Enter. */
export function NicknameInput({
  value,
  onChange,
  name,
}: {
  value: string[];
  onChange: (v: string[]) => void;
  /** The protocol's generated name: a nickname equal to it is refused. */
  name?: string;
}) {
  const [draft, setDraft] = useState("");
  const isName = !!name && draft.trim().toLowerCase() === name.trim().toLowerCase();
  const add = () => {
    const label = draft.trim();
    if (isName) return;
    setDraft("");
    if (!label || value.some((n) => n.toLowerCase() === label.toLowerCase())) return;
    onChange([...value, label]);
  };
  return (
    <div className="grid gap-2">
      <Label htmlFor="protocol-nicknames">Also known as</Label>
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {value.map((n) => (
            <Badge key={n} variant="secondary">
              {n}
              <button
                type="button"
                aria-label={`Remove ${n}`}
                onClick={() => onChange(value.filter((x) => x !== n))}
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}
      <Input
        id="protocol-nicknames"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key !== "Enter") return;
          e.preventDefault();
          add();
        }}
        // Typed but not yet entered when Create is clicked: keep it rather than drop it.
        onBlur={add}
        placeholder="e.g. MABA, HLM CLint (Enter to add)"
        className="max-w-sm"
        aria-invalid={isName}
        aria-describedby={isName ? "protocol-nicknames-hint" : undefined}
      />
      {isName && (
        <p id="protocol-nicknames-hint" className="text-xs text-destructive">
          That is already the protocol's name; a nickname must differ.
        </p>
      )}
    </div>
  );
}
