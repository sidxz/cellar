"use client";

import { useEffect, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { useGetUnregisteredRowsApiV1CollectionImportPreviewsPreviewIdUnregisteredRowsGet as useUnregisteredRows } from "@/shared/lib/api/collection-import/collection-import";
import type { UnregisteredRowResponse } from "@/shared/lib/api/model";
import { useRegistrationWizard } from "./use-registration-wizard";

// CSV columns recognised by the bulk-register CSV importer.
// Source of truth: CSV_TEMPLATE_HEADERS in step-input.tsx.
// The handoff only populates the columns the upstream stash carries.
const CSV_HEADERS = [
  "name",
  "smiles",
  "identifier",
  "identifier_type",
] as const;

function escapeCsvCell(value: string): string {
  // Quote everything that's non-empty for safety — CSV parsers handle quoted
  // cells uniformly and we avoid edge cases around commas / quotes / newlines
  // in molecule names + notes.
  return `"${value.replace(/"/g, '""')}"`;
}

function buildCsvFromStash(rows: UnregisteredRowResponse[]): File {
  const lines: string[] = [CSV_HEADERS.join(",")];
  for (const r of rows) {
    const name = r.name ?? "";
    const smiles = r.smiles ?? "";
    const identifier = r.external_id ?? "";
    const identifierType = identifier ? "custom" : "";
    lines.push(
      [name, smiles, identifier, identifierType].map(escapeCsvCell).join(","),
    );
  }
  const csv = lines.join("\n");
  return new File([csv], "from-collection-import.csv", { type: "text/csv" });
}

/**
 * Wires the bulk-register wizard to a collection-import stash.
 *
 * When `?from_collection_import=<preview_id>` is present in the URL, this
 * hook fetches the stash of unregistered rows from the collection-import
 * preview, converts them to a CSV file, and injects it into the wizard's
 * bulkInput state — also forcing the wizard into "bulk" mode.
 *
 * The injection runs exactly once per preview id so chemists can navigate
 * back/forward without losing their work.
 */
export function useCollectionImportHandoff() {
  const searchParams = useSearchParams();
  const fromImport = searchParams.get("from_collection_import");

  const mode = useRegistrationWizard((s) => s.mode);
  const setMode = useRegistrationWizard((s) => s.setMode);
  const updateBulkInput = useRegistrationWizard((s) => s.updateBulkInput);

  const stash = useUnregisteredRows(fromImport ?? "", {
    query: { enabled: !!fromImport },
  });

  // Track which preview id we've already injected so we don't keep
  // overwriting a chemist's edits if they navigate back to the input step.
  const injectedRef = useRef<string | null>(null);

  // Flip into bulk mode as soon as the handoff param is detected, so the
  // chemist doesn't briefly see the mode-selection screen while the stash
  // fetch is in-flight.
  useEffect(() => {
    if (!fromImport) return;
    if (mode !== "bulk") setMode("bulk");
  }, [fromImport, mode, setMode]);

  useEffect(() => {
    if (!fromImport) return;
    if (!stash.data) return;
    if (injectedRef.current === fromImport) return;

    const file = buildCsvFromStash(stash.data.rows);
    updateBulkInput({ file, fileFormat: "csv" });
    injectedRef.current = fromImport;
  }, [fromImport, stash.data, updateBulkInput]);
}
