"use client";

import type { ProtocolForm } from "@/features/workspace-config/hooks/use-protocol-forms";
import { Button } from "@/shared/components/ui/button";
import { Label } from "@/shared/components/ui/label";

/** The category's forms as one-click starting points, named for what the protocol reports
 *  (IC50 dose-response, Ki, MIC...); "Custom" starts with no readouts. */
export function StartsFrom({
  forms,
  selectedId,
  onPick,
}: {
  forms: ProtocolForm[];
  selectedId: string | null;
  onPick: (form: ProtocolForm | null) => void;
}) {
  if (forms.length === 0) return null;
  return (
    <div className="grid gap-2">
      <Label>What it reports</Label>
      <div className="flex flex-wrap gap-2">
        {forms.map((f) => (
          <Button
            key={f.id}
            type="button"
            size="sm"
            variant={f.id === selectedId ? "default" : "outline"}
            aria-pressed={f.id === selectedId}
            onClick={() => onPick(f)}
          >
            {f.name}
          </Button>
        ))}
        <Button type="button" size="sm" variant="outline" onClick={() => onPick(null)}>
          Custom
        </Button>
      </div>
    </div>
  );
}
