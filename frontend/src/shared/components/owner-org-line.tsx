"use client";

import { DuarOrgSelect } from "@/shared/components/duar-org-select";
import { Button } from "@/shared/components/ui/button";
import { useOrgName } from "@/shared/hooks/use-orgs";
import { Pencil } from "lucide-react";
import { useState } from "react";

/**
 * "Owned by <org>" for a collection, project or protocol. Someone who may change it
 * (an admin or the creator) clicks the org, picks another one and saves — nothing
 * changes until Save. Escape cancels.
 */
export function OwnerOrgLine({
  ownerOrgId,
  canChange,
  onSave,
}: {
  ownerOrgId: string | null | undefined;
  canChange: boolean;
  onSave: (orgId: string) => Promise<unknown>;
}) {
  const orgName = useOrgName();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string | null>(ownerOrgId ?? null);
  const [saving, setSaving] = useState(false);

  const cancel = () => {
    setDraft(ownerOrgId ?? null);
    setEditing(false);
  };
  const save = async () => {
    if (!draft || draft === ownerOrgId) return;
    setSaving(true);
    try {
      await onSave(draft);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  if (editing) {
    return (
      <div
        className="flex flex-wrap items-center gap-2 text-sm"
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.preventDefault();
            cancel();
          }
        }}
      >
        <span className="text-muted-foreground">Owned by</span>
        <div className="w-64">
          <DuarOrgSelect value={draft} onValueChange={setDraft} />
        </div>
        <Button type="button" variant="outline" size="sm" onClick={cancel} disabled={saving}>
          Cancel
        </Button>
        <Button
          type="button"
          size="sm"
          onClick={save}
          disabled={saving || !draft || draft === ownerOrgId}
        >
          {saving ? "Saving…" : "Save"}
        </Button>
      </div>
    );
  }

  const name = ownerOrgId ? orgName(ownerOrgId) : "No org";
  if (!canChange) {
    return (
      <span className="text-sm text-muted-foreground">
        Owned by <span className="font-medium text-foreground">{name}</span>
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-sm text-muted-foreground">
      Owned by
      <button
        type="button"
        onClick={() => {
          setDraft(ownerOrgId ?? null);
          setEditing(true);
        }}
        aria-label={`Change owner (${name})`}
        className="group inline-flex items-center gap-1 rounded-md px-1 py-0.5 font-medium text-foreground transition-colors hover:bg-muted/50 focus:bg-muted/60 focus:outline-none"
      >
        {name}
        <Pencil className="h-3 w-3 text-muted-foreground/40 group-hover:text-muted-foreground" />
      </button>
    </span>
  );
}
