"use client";

import { Button } from "@/shared/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import { Input } from "@/shared/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { ReferenceKind } from "@/shared/lib/api/model";
import { X } from "lucide-react";
import { useState } from "react";
import { useAddProtocolReference, useRemoveProtocolReference } from "../hooks/use-protocols";
import {
  REFERENCE_KIND_LABELS,
  REFERENCE_KIND_PLACEHOLDERS,
  normalizeReference,
  referenceHref,
  referenceKey,
} from "../lib/protocol-references";
import type { Protocol, ProtocolReference } from "../types";

interface ReferencesEditorProps {
  references: ProtocolReference[];
  /** A rejected promise keeps the typed value (the caller already said why). */
  onAdd: (reference: ProtocolReference) => unknown;
  onRemove: (reference: ProtocolReference) => void;
  canEdit: boolean;
  pending?: boolean;
}

/** Typed references with links built only from validated values. No <form>: it also sits inside
 *  the create dialog's form, so Enter and the button add explicitly. */
export function ReferencesEditor({
  references,
  onAdd,
  onRemove,
  canEdit,
  pending,
}: ReferencesEditorProps) {
  const [kind, setKind] = useState<ReferenceKind>(ReferenceKind.doi);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  const add = async () => {
    const checked = normalizeReference(kind, draft);
    if ("error" in checked) return setError(checked.error);
    const reference = { kind, value: checked.value };
    if (references.some((r) => referenceKey(r) === referenceKey(reference))) {
      return setError("Already listed");
    }
    setError(null);
    try {
      await onAdd(reference);
      setDraft("");
    } catch {
      // The mutation's toast says why; keep the value for fixing.
    }
  };

  return (
    <div className="grid gap-2">
      {references.length === 0 && !canEdit && (
        <p className="text-sm text-muted-foreground">No references.</p>
      )}
      {references.length > 0 && (
        <ul className="space-y-1 text-sm">
          {references.map((r) => {
            const href = referenceHref(r);
            const label = REFERENCE_KIND_LABELS[r.kind] ?? r.kind;
            return (
              <li key={referenceKey(r)} className="flex items-center gap-2">
                <span className="w-24 shrink-0 text-xs text-muted-foreground">{label}</span>
                {href ? (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="min-w-0 truncate text-primary underline-offset-2 hover:underline"
                  >
                    {r.value}
                  </a>
                ) : (
                  <span className="min-w-0 truncate">{r.value}</span>
                )}
                {canEdit && (
                  <button
                    type="button"
                    aria-label={`Remove ${label} ${r.value}`}
                    onClick={() => onRemove(r)}
                    className="rounded p-0.5 hover:bg-muted"
                  >
                    <X className="h-3 w-3" />
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {canEdit && (
        <div className="flex flex-wrap items-start gap-2">
          <Select value={kind} onValueChange={(v) => setKind(v as ReferenceKind)}>
            <SelectTrigger className="w-36" aria-label="Reference kind">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.values(ReferenceKind).map((k) => (
                <SelectItem key={k} value={k}>
                  {REFERENCE_KIND_LABELS[k]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="grid gap-1">
            <Input
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value);
                setError(null);
              }}
              onKeyDown={(e) => {
                if (e.key !== "Enter") return;
                e.preventDefault();
                void add();
              }}
              placeholder={REFERENCE_KIND_PLACEHOLDERS[kind]}
              aria-label="Reference value"
              aria-invalid={!!error}
              className="w-72"
            />
            {error && <p className="text-xs text-destructive">{error}</p>}
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-label="Add reference"
            disabled={!draft.trim() || pending}
            onClick={() => void add()}
          >
            Add
          </Button>
        </div>
      )}
    </div>
  );
}

/** Overview card: where this protocol comes from. Draft and active take changes; the API refuses
 *  them on locked and retired protocols. */
export function ProtocolReferencesCard({
  protocol,
  canEdit,
}: {
  protocol: Protocol;
  canEdit: boolean;
}) {
  const add = useAddProtocolReference(protocol.id);
  const remove = useRemoveProtocolReference(protocol.id);
  return (
    <Card>
      <CardHeader>
        <CardTitle>References</CardTitle>
        <CardDescription>
          Where this protocol comes from: the assay record (ChEMBL, PubChem) or the paper.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ReferencesEditor
          references={protocol.references ?? []}
          onAdd={(r) => add.mutateAsync(r)}
          onRemove={(r) => remove.mutate(r)}
          canEdit={canEdit}
          pending={add.isPending}
        />
      </CardContent>
    </Card>
  );
}
