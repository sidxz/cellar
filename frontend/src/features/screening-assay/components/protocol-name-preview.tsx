"use client";

import type { NamePreviewResponse } from "@/shared/lib/api/model";
import { Loader2 } from "lucide-react";

/** Complete, unique, and with a valid discriminator: the protocol can be created. */
export function isPreviewSavable(p?: NamePreviewResponse): boolean {
  return (
    !!p && p.missing.length === 0 && !p.clash && !p.needs_discriminator && !p.discriminator_error
  );
}

export function ProtocolNamePreview({
  preview,
  isFetching,
}: {
  preview?: NamePreviewResponse;
  isFetching: boolean;
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
        The code is assigned when you create the protocol.
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
          Other protocols are also "{preview.base}" (
          {preview.siblings.map((s) => s.code).join(", ")}). Add a discriminator, such as the
          method.
        </p>
      )}
      {preview.discriminator_error && (
        <p className="mt-2 text-sm text-destructive">{preview.discriminator_error}</p>
      )}
    </div>
  );
}
