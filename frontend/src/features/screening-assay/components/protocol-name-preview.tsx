"use client";

import { useProtocolCategories } from "@/features/workspace-config/hooks/use-protocol-categories";
import type { NamePreviewResponse } from "@/shared/lib/api/model";
import { Loader2 } from "lucide-react";

/** Slots a category pattern needs filled: `{slot}` without `?` (same rule as the backend). */
export function requiredNameSlots(pattern?: string | null): Set<string> {
  return new Set([...(pattern ?? "").matchAll(/\{([a-z_]+)\}/g)].map((m) => m[1]));
}

/** The slots the named category's pattern needs, so a form can stop calling them optional. */
export function useRequiredNameSlots(category?: string | null): Set<string> {
  const { data } = useProtocolCategories();
  return requiredNameSlots(data?.find((c) => c.label === category)?.name_pattern);
}

/** Complete, unique, and with a valid discriminator: the protocol can be created. */
export function isPreviewSavable(p?: NamePreviewResponse): boolean {
  return (
    !!p && p.missing.length === 0 && !p.clash && !p.needs_discriminator && !p.discriminator_error
  );
}

export function ProtocolNamePreview({
  preview,
  isFetching,
  code,
}: {
  preview?: NamePreviewResponse;
  isFetching: boolean;
  /** The protocol's code when it already exists (edit, correct); otherwise it comes on create. */
  code?: string | null;
}) {
  if (!preview) {
    return <p className="text-sm text-muted-foreground">Pick a category to see the name.</p>;
  }
  return (
    <div className="rounded-md border bg-muted/40 p-3" aria-live="polite">
      <div className="flex items-center gap-2">
        <span className="text-xs uppercase tracking-wide text-muted-foreground">Name</span>
        {isFetching && (
          <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" aria-hidden />
        )}
      </div>
      <p className="mt-1 font-medium">{preview.name}</p>
      <p className="text-xs text-muted-foreground">
        {code ? `Code ${code}` : "The code is assigned when you create the protocol."}
      </p>
      {preview.missing_labels.length > 0 && (
        <p className="mt-2 text-sm text-amber-700 dark:text-amber-400">
          This name needs {preview.missing_labels.join(", ")}.
        </p>
      )}
      {preview.clash && (
        <p className="mt-2 text-sm text-destructive">
          {preview.clash.code} already has this exact name. Use a different discriminator.
        </p>
      )}
      {!preview.clash && preview.needs_discriminator && (
        <p className="mt-2 text-sm text-amber-700 dark:text-amber-400">
          Other protocols share the name "{preview.base}":{" "}
          {preview.siblings.map((s) => `${s.code} ${s.name}`).join(", ")}. Add a discriminator, such
          as the method.
        </p>
      )}
      {preview.discriminator_error && (
        <p className="mt-2 text-sm text-destructive">{preview.discriminator_error}</p>
      )}
    </div>
  );
}
