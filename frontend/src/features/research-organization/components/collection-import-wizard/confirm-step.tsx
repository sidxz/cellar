"use client";

import Link from "next/link";

import { Button } from "@/shared/components/ui/button";

export interface ConfirmStepProps {
  result: {
    resolved_count: number;
    already_present_count: number;
    unregistered_count: number;
    error_count: number;
    preview_id?: string | null;
  };
  collectionId: string;
  onClose: () => void;
}

export function ConfirmStep({ result, collectionId, onClose }: ConfirmStepProps) {
  // Registration opens in a new tab; route is /compounds/register, which reads
  // ?from_collection_import to pre-fill the bulk step.
  const handoffHref = result.preview_id
    ? `/compounds/register?from_collection_import=${result.preview_id}`
    : null;
  return (
    <div className="space-y-4">
      <div className="rounded border bg-emerald-50 p-4">
        <p className="font-medium">{result.resolved_count} molecules added</p>
        <p className="text-sm text-muted-foreground">
          {result.already_present_count} already present ·{" "}
          {result.unregistered_count + result.error_count} skipped
        </p>
      </div>
      {handoffHref && result.unregistered_count > 0 && (
        <div className="rounded border border-amber-300 bg-amber-50 p-3">
          <p className="text-sm text-amber-900">
            {result.unregistered_count} rows weren&apos;t added because they aren&apos;t registered
            yet.
          </p>
          <Link
            href={handoffHref}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-2 inline-block text-sm font-medium underline"
          >
            Register them ↗ (opens a new tab)
          </Link>
        </div>
      )}
      <div className="flex gap-2">
        <Link href={`/collections/${collectionId}`}>
          <Button variant="default">Back to collection</Button>
        </Link>
        <Button variant="outline" onClick={onClose}>
          Import another file
        </Button>
      </div>
    </div>
  );
}
