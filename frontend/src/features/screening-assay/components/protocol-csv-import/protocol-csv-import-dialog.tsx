"use client";

import { CsvDropzone } from "@/shared/components/csv-dropzone";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Table, TableBody, TableHead, TableHeader, TableRow } from "@/shared/components/ui/table";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { saveText } from "@/shared/lib/api/download";
import { parseCsv } from "@/shared/lib/parse-csv";
import { useQueries, useQueryClient } from "@tanstack/react-query";
import { Download } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { PROTOCOLS_KEY } from "../../hooks/query-keys";
import { useProtocolCsvContext } from "../../hooks/use-protocol-csv-context";
import { useProtocolFacetSlots } from "../../hooks/use-protocol-facet-slots";
import { namePreviewQuery } from "../../hooks/use-protocol-name-preview";
import {
  type ProtocolCsvRow,
  type RowPicks,
  inFileClashes,
  protocolCsvTemplate,
  readProtocolCsv,
  resolveRow,
  rowBlockers,
  rowCreatePayload,
} from "../../lib/protocol-csv-import";
import type { Protocol } from "../../types";
import { isPreviewSavable } from "../protocol-name-preview";
import { ImportRow } from "./import-row";

interface FileRow {
  /** The file line (header is line 1): how the chemist finds the row in the spreadsheet. */
  line: number;
  csv: ProtocolCsvRow;
  picks: RowPicks;
  error: string | null;
}

// ApiError.message reads "API error: 409 — <detail>"; the detail alone tells the chemist what to fix.
const errorText = (e: unknown) =>
  (e instanceof Error ? e.message : String(e)).replace(/^API error: \d+ — /, "");

/** Protocols from a CSV: upload, resolve every row in place, then create the ready ones on request. */
export function ProtocolCsvImportDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const qc = useQueryClient();
  const facetSlots = useProtocolFacetSlots();
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [rows, setRows] = useState<FileRow[]>([]);
  const [created, setCreated] = useState<Protocol[]>([]);
  const [creating, setCreating] = useState(false);

  const ctx = useProtocolCsvContext(rows.map((r) => r.csv));
  const resolved = ctx ? rows.map((r) => resolveRow(r.csv, ctx, r.picks)) : [];
  // One preview per distinct draft: rows with the same facts share it (and clash).
  const draftKeys = resolved.map((r) => (r.draft ? JSON.stringify(r.draft) : null));
  const uniqueKeys = [...new Set(draftKeys.filter((k): k is string => k !== null))];
  const results = useQueries({ queries: uniqueKeys.map((k) => namePreviewQuery(k)) });
  const previews = draftKeys.map((k) => (k ? results[uniqueKeys.indexOf(k)]?.data : undefined));
  const clashes = inFileClashes(previews.map((p) => p?.name));
  const blockers = resolved.map((r, i) => {
    const other = clashes.get(i);
    return rowBlockers(r, previews[i], other === undefined ? null : rows[other].line);
  });
  const ready = resolved
    .map((_, i) => i)
    .filter((i) => blockers[i].length === 0 && isPreviewSavable(previews[i]));

  async function onFile(f: File) {
    setFile(f);
    setFileError(null);
    const parsed = await parseCsv(f);
    const read = parsed.kind === "ok" ? readProtocolCsv(parsed) : { error: parsed.message };
    if ("error" in read) {
      setFileError(read.error);
      return;
    }
    if (read.rows.length === 0) {
      setFileError("The file has no rows.");
      return;
    }
    setRows(read.rows.map((csv, i) => ({ line: i + 2, csv, picks: {}, error: null })));
  }

  const pick = (line: number, picks: RowPicks) =>
    setRows((prev) =>
      prev.map((r) =>
        r.line === line ? { ...r, picks: { ...r.picks, ...picks }, error: null } : r,
      ),
    );

  // One at a time, in file order: a created row leaves the table, a refused one stays with why.
  async function createReady() {
    setCreating(true);
    for (const i of ready) {
      const { line } = rows[i];
      try {
        const protocol = await customInstance<Protocol>({
          url: `${API_V1}/protocols`,
          method: "POST",
          data: rowCreatePayload(resolved[i]),
        });
        setCreated((prev) => [...prev, protocol]);
        setRows((prev) => prev.filter((r) => r.line !== line));
      } catch (e) {
        setRows((prev) => prev.map((r) => (r.line === line ? { ...r, error: errorText(e) } : r)));
      }
    }
    // Names now in use refresh every remaining row's preview (previews live under the protocols key).
    await qc.invalidateQueries({ queryKey: PROTOCOLS_KEY });
    setCreating(false);
  }

  const reset = () => {
    setFile(null);
    setFileError(null);
    setRows([]);
    setCreated([]);
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !creating && onOpenChange(o)}>
      <DialogContent className="w-[min(95vw,1400px)] max-w-[1400px] sm:max-w-[1400px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Import protocols (CSV)</DialogTitle>
          <DialogDescription>
            One protocol per row. Nicknames and references are separated by ";", and a reference is
            kind:value (doi, pmid, url, chembl_assay, pubchem_aid). A blank form means the
            category's default.
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-center justify-between gap-2">
          <p className="text-sm text-muted-foreground">
            {file ? `File: ${file.name}` : "Start from the template."}
          </p>
          <div className="flex gap-2">
            {file && (
              <Button variant="ghost" size="sm" onClick={reset} disabled={creating}>
                Choose another file
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={() => saveText(protocolCsvTemplate(), "protocol-import-template.csv")}
            >
              <Download className="mr-2 h-4 w-4" />
              Download Template
            </Button>
          </div>
        </div>

        {rows.length === 0 && created.length === 0 && (
          <CsvDropzone
            file={file}
            onFile={(f) => void onFile(f)}
            accept={{ "text/csv": [".csv"] }}
            prompt="Drop a CSV here, or click to browse"
          />
        )}
        {fileError && <p className="text-sm text-destructive">{fileError}</p>}

        {created.length > 0 && (
          <div className="rounded-md border border-emerald-600/30 bg-emerald-600/5 p-3 text-sm">
            <p className="font-medium">Created {created.length}</p>
            <ul className="mt-1 space-y-0.5">
              {created.map((p) => (
                <li key={p.id}>
                  <Link href={`/assays/protocols/${p.id}`} className="underline">
                    {p.code}
                  </Link>{" "}
                  {p.name}
                </li>
              ))}
            </ul>
          </div>
        )}

        {rows.length > 0 &&
          (ctx ? (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Row</TableHead>
                    <TableHead>Name</TableHead>
                    <TableHead>Category</TableHead>
                    <TableHead>Form</TableHead>
                    <TableHead>Facts</TableHead>
                    <TableHead>Discriminator</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((r, i) => (
                    <ImportRow
                      key={r.line}
                      line={r.line}
                      row={resolved[i]}
                      preview={previews[i]}
                      blockers={blockers[i]}
                      error={r.error}
                      categories={ctx.categories}
                      forms={ctx.forms}
                      targets={ctx.targets}
                      facetSlots={facetSlots}
                      onPick={(picks) => pick(r.line, picks)}
                    />
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Loading categories, forms and targets…</p>
          ))}

        <DialogFooter>
          {rows.length > 0 && (
            <Button onClick={() => void createReady()} disabled={ready.length === 0 || creating}>
              {creating
                ? "Creating…"
                : `Create ${ready.length} protocol${ready.length === 1 ? "" : "s"}`}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
