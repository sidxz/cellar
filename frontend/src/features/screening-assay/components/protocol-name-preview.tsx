"use client";

import { useProtocolCategories } from "@/features/workspace-config/hooks/use-protocol-categories";
import type { NamePreviewResponse } from "@/shared/lib/api/model";
import { Loader2 } from "lucide-react";

/** The slots a category pattern places: `{slot}` is required, `{slot?}` optional (same rule as the backend). */
export function nameSlots(pattern?: string | null): {
  required: Set<string>;
  optional: Set<string>;
} {
  const required = new Set<string>();
  const optional = new Set<string>();
  for (const [, slot, mark] of (pattern ?? "").matchAll(/\{([a-z_]+)(\?)?\}/g)) {
    (mark ? optional : required).add(slot);
  }
  return { required, optional };
}

/** The slots the named category's pattern places. */
export function useNameSlots(category?: string | null) {
  const { data } = useProtocolCategories();
  return nameSlots(data?.find((c) => c.label === category)?.name_pattern);
}

/** The slots the named category's pattern needs, so a form can stop calling them optional. */
export function useRequiredNameSlots(category?: string | null): Set<string> {
  return useNameSlots(category).required;
}

/** Complete, unique, with a valid discriminator, and no sibling rename clashes: the protocol can be created. */
export function isPreviewSavable(p?: NamePreviewResponse): boolean {
  return (
    !!p &&
    p.missing.length === 0 &&
    !p.clash &&
    !p.needs_discriminator &&
    !p.discriminator_error &&
    !(p.sibling_renames ?? []).some((r) => r.error)
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
