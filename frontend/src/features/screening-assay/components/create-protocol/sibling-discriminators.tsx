"use client";

import { Input } from "@/shared/components/ui/input";
import type {
  NameSiblingResponse,
  SiblingDiscriminatorRequest,
  SiblingRenameResponse,
} from "@/shared/lib/api/model";

export type SiblingValues = Record<string, { discriminator: string; reason: string }>;

const offered = (s: NameSiblingResponse) =>
  !s.discriminator && !s.is_locked && s.status !== "retired";

/** The prefilled correction reason for a published sibling. */
export const siblingReason = (newName: string) => `Distinguish from the new protocol (${newName})`;

/** What one save sends: filled fields of siblings still offered, a reason for published ones. */
export function siblingDiscriminatorsPayload(
  siblings: NameSiblingResponse[],
  values: SiblingValues,
  newName: string,
): SiblingDiscriminatorRequest[] {
  return siblings.filter(offered).flatMap((s) => {
    const v = values[s.protocol_id];
    const discriminator = v?.discriminator.trim();
    if (!discriminator) return [];
    const reason = s.status === "active" ? v.reason.trim() || siblingReason(newName) : null;
    return [{ protocol_id: s.protocol_id, discriminator, reason }];
  });
}

export function SiblingDiscriminators({
  siblings,
  renames,
  values,
  newName,
  onChange,
}: {
  siblings: NameSiblingResponse[];
  renames: SiblingRenameResponse[];
  values: SiblingValues;
  newName: string;
  onChange: (v: SiblingValues) => void;
}) {
  const bare = siblings.filter((s) => !s.discriminator);
  if (bare.length === 0) return null;
  return (
    <div className="space-y-2 rounded-md border border-amber-300/60 bg-amber-50/60 p-3 text-sm">
      {bare.map((s) => {
        const v = values[s.protocol_id] ?? { discriminator: "", reason: "" };
        const rename = renames.find((r) => r.protocol_id === s.protocol_id);
        if (!offered(s)) {
          return (
            <p key={s.protocol_id} className="text-amber-900">
              {s.code} ({s.status === "retired" ? "retired" : "locked"}) keeps its name and is
              flagged for its owner.
            </p>
          );
        }
        const reason = v.reason || siblingReason(newName);
        return (
          <div key={s.protocol_id} className="grid gap-1">
            <label className="flex items-center gap-2">
              <span className="shrink-0 text-amber-900">
                {s.code} becomes {s.name} [
              </span>
              <Input
                aria-label={`Discriminator for ${s.code}`}
                className="h-8"
                value={v.discriminator}
                onChange={(e) =>
                  onChange({
                    ...values,
                    [s.protocol_id]: { discriminator: e.target.value, reason: v.reason },
                  })
                }
              />
              <span className="text-amber-900">]</span>
            </label>
            {rename?.name && !rename.error && (
              <span className="text-xs text-muted-foreground">{rename.name}</span>
            )}
            {rename?.error && <span className="text-xs text-destructive">{rename.error}</span>}
            {s.status === "active" && (
              <Input
                aria-label={`Correction reason for ${s.code}`}
                className="h-8"
                value={reason}
                onChange={(e) =>
                  onChange({
                    ...values,
                    [s.protocol_id]: { discriminator: v.discriminator, reason: e.target.value },
                  })
                }
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
