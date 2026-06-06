"use client";

import { useMoleculeSearch } from "@/features/chemical-registration/hooks/use-molecules";
import type { Molecule } from "@/features/chemical-registration/types";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { SearchInput } from "@/shared/components/search-input";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";
import { Textarea } from "@/shared/components/ui/textarea";
import { saveText } from "@/shared/lib/api/download";
import { parseCsv } from "@/shared/lib/parse-csv";
import { SEARCH_MIN_QUERY_LEN } from "@/shared/lib/timing";
import type { ColDef, GridApi } from "ag-grid-community";
import { ChevronDown, ChevronRight, Download, Upload } from "lucide-react";
import { useCallback, useMemo, useRef, useState } from "react";
import { useAddMolecules } from "../hooks/use-collection-molecules";
import type { MembershipResult, MoleculeReference, RefType } from "../types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AddMoleculesDialogProps {
  collectionId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface MoleculeSearchRow {
  id: string;
  name: string;
  registration_number: string;
}

// ---------------------------------------------------------------------------
// Shared result display
// ---------------------------------------------------------------------------

function MembershipResultDisplay({ result }: { result: MembershipResult }) {
  const [showUnresolved, setShowUnresolved] = useState(false);

  return (
    <div className="space-y-2 rounded-md border p-3 text-sm">
      <div className="flex items-center gap-4">
        <span className="text-success font-medium">Added {result.added_count}</span>
        {result.already_present > 0 && (
          <span className="text-muted-foreground">{result.already_present} already present</span>
        )}
      </div>
      {result.unresolved.length > 0 && (
        <div>
          <button
            type="button"
            className="flex items-center gap-1 text-destructive font-medium hover:underline"
            onClick={() => setShowUnresolved(!showUnresolved)}
          >
            {showUnresolved ? (
              <ChevronDown className="h-3.5 w-3.5" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" />
            )}
            Failed ({result.unresolved.length})
          </button>
          {showUnresolved && (
            <div className="mt-2 overflow-x-auto rounded-md border">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-3 py-1.5 text-left">Value</th>
                    <th className="px-3 py-1.5 text-left">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {result.unresolved.map((u, i) => (
                    <tr key={i} className="border-b last:border-0">
                      <td className="px-3 py-1.5 font-mono">{u.value}</td>
                      <td className="px-3 py-1.5 text-destructive">{u.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CSV helpers
// ---------------------------------------------------------------------------

function downloadTemplate() {
  const header = "identifier,type";
  const row1 = "CC-000001,registration_number";
  const row2 = "aspirin,name";
  saveText([header, row1, row2].join("\n"), "add-molecules-template.csv");
}

/**
 * Parse an uploaded CSV (header row: `identifier,type`) into add-molecule rows.
 * Uses the shared PapaParse-based parser so quoted/comma-containing identifiers
 * round-trip correctly. Unknown/missing type defaults to "name".
 */
async function parseCSV(file: File): Promise<Array<{ identifier: string; type: string }>> {
  const parsed = await parseCsv(file);
  if (parsed.kind !== "ok") return [];
  return parsed.rows.map((row) => ({
    identifier: row.identifier ?? "",
    type: row.type || "name",
  }));
}

// Map friendly labels to RefType values
const PASTE_REF_TYPES: { value: RefType; label: string }[] = [
  { value: "registration_number", label: "Registration Number" },
  { value: "external_id", label: "External ID" },
  { value: "smiles", label: "SMILES" },
  { value: "inchi_key", label: "InChI Key" },
  { value: "name", label: "Name" },
];

// ---------------------------------------------------------------------------
// Search Tab
// ---------------------------------------------------------------------------

function SearchTab({
  collectionId,
  onResult,
}: {
  collectionId: string;
  onResult: (result: MembershipResult) => void;
}) {
  const [searchTerm, setSearchTerm] = useState("");
  const { data: results, isLoading: searching } = useMoleculeSearch(searchTerm);
  const addMutation = useAddMolecules(collectionId);
  const gridApiRef = useRef<GridApi<MoleculeSearchRow> | null>(null);

  const rows: MoleculeSearchRow[] = useMemo(
    () =>
      (results ?? []).map((m: Molecule) => ({
        id: m.id,
        name: m.name,
        registration_number: m.registration_number,
      })),
    [results],
  );

  const columnDefs = useMemo<ColDef<MoleculeSearchRow>[]>(
    () => [
      {
        headerName: "Reg #",
        field: "registration_number",
        width: 140,
        cellClass: "font-mono text-xs",
      },
      { headerName: "Name", field: "name", flex: 1 },
    ],
    [],
  );

  const handleAdd = useCallback(() => {
    const selected = gridApiRef.current?.getSelectedRows() ?? [];
    if (selected.length === 0) return;
    const refs: MoleculeReference[] = selected.map((r) => ({
      value: r.id,
      ref_type: "uuid" as RefType,
    }));
    addMutation.mutate(
      { references: refs },
      {
        onSuccess: (result) => onResult(result),
      },
    );
  }, [addMutation, onResult]);

  return (
    <div className="space-y-3 pt-2">
      <SearchInput
        value={searchTerm}
        onChange={setSearchTerm}
        placeholder="Search by name, reg number, or identifier..."
      />

      <DataGrid<MoleculeSearchRow>
        rowData={rows}
        columnDefs={columnDefs}
        loading={searching && searchTerm.length >= SEARCH_MIN_QUERY_LEN}
        height="250px"
        suppressFilters
        rowSelection="multiple"
        onSelectionChanged={(e) => {
          gridApiRef.current = e.api;
        }}
        emptyState={
          searchTerm.length < SEARCH_MIN_QUERY_LEN ? (
            <div className="flex items-center justify-center rounded-lg border border-dashed p-8 text-center">
              <p className="text-sm text-muted-foreground">Type at least 2 characters to search.</p>
            </div>
          ) : (
            <div className="flex items-center justify-center rounded-lg border border-dashed p-8 text-center">
              <p className="text-sm text-muted-foreground">No molecules found.</p>
            </div>
          )
        }
      />

      <div className="flex justify-end">
        <Button size="sm" onClick={handleAdd} disabled={addMutation.isPending}>
          {addMutation.isPending ? "Adding..." : "Add Selected"}
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Paste Tab
// ---------------------------------------------------------------------------

function PasteTab({
  collectionId,
  onResult,
}: {
  collectionId: string;
  onResult: (result: MembershipResult) => void;
}) {
  const [text, setText] = useState("");
  const [refType, setRefType] = useState<RefType>("registration_number");
  const addMutation = useAddMolecules(collectionId);

  const handleAdd = () => {
    const lines = text
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l.length > 0);
    if (lines.length === 0) return;

    const refs: MoleculeReference[] = lines.map((value) => ({
      value,
      ref_type: refType,
    }));
    addMutation.mutate(
      { references: refs },
      {
        onSuccess: (result) => onResult(result),
      },
    );
  };

  return (
    <div className="space-y-3 pt-2">
      <div className="grid gap-2">
        <Label className="text-xs">Identifier Type</Label>
        <Select value={refType} onValueChange={(v) => setRefType(v as RefType)}>
          <SelectTrigger className="w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PASTE_REF_TYPES.map((t) => (
              <SelectItem key={t.value} value={t.value}>
                {t.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Textarea
        placeholder="Paste identifiers, one per line"
        rows={8}
        className="font-mono text-xs"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />

      <div className="flex justify-end">
        <Button
          size="sm"
          onClick={handleAdd}
          disabled={addMutation.isPending || text.trim().length === 0}
        >
          {addMutation.isPending ? "Adding..." : "Add"}
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// CSV Tab
// ---------------------------------------------------------------------------

function CsvTab({
  collectionId,
  onResult,
}: {
  collectionId: string;
  onResult: (result: MembershipResult) => void;
}) {
  const [parsedRows, setParsedRows] = useState<Array<{ identifier: string; type: string }>>([]);
  const [fileName, setFileName] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const addMutation = useAddMolecules(collectionId);

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    void parseCSV(file).then(setParsedRows);
    e.target.value = "";
  };

  const handleImport = () => {
    if (parsedRows.length === 0) return;

    const validTypes: RefType[] = [
      "registration_number",
      "external_id",
      "smiles",
      "inchi_key",
      "name",
    ];
    const refs: MoleculeReference[] = parsedRows.map((row) => ({
      value: row.identifier,
      ref_type: validTypes.includes(row.type as RefType) ? (row.type as RefType) : "name",
    }));
    addMutation.mutate(
      { references: refs },
      {
        onSuccess: (result) => onResult(result),
      },
    );
  };

  return (
    <div className="space-y-3 pt-2">
      <div className="flex items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={downloadTemplate}>
          <Download className="mr-1 h-3 w-3" />
          Download Template
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => fileInputRef.current?.click()}
        >
          <Upload className="mr-1 h-3 w-3" />
          Upload CSV
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={handleFileUpload}
        />
        {fileName && <span className="text-xs text-muted-foreground">{fileName}</span>}
      </div>

      {/* Preview table */}
      {parsedRows.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">
            Preview ({parsedRows.length} row
            {parsedRows.length !== 1 ? "s" : ""}, showing first 10)
          </p>
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-3 py-1.5 text-left">#</th>
                  <th className="px-3 py-1.5 text-left">Identifier</th>
                  <th className="px-3 py-1.5 text-left">Type</th>
                </tr>
              </thead>
              <tbody>
                {parsedRows.slice(0, 10).map((row, i) => (
                  <tr key={i} className="border-b last:border-0">
                    <td className="px-3 py-1.5 text-muted-foreground">{i + 1}</td>
                    <td className="px-3 py-1.5 font-mono text-xs">{row.identifier}</td>
                    <td className="px-3 py-1.5">{row.type}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {parsedRows.length > 10 && (
            <p className="text-xs text-muted-foreground">
              ...and {parsedRows.length - 10} more rows
            </p>
          )}
        </div>
      )}

      <div className="flex justify-end">
        <Button
          size="sm"
          onClick={handleImport}
          disabled={addMutation.isPending || parsedRows.length === 0}
        >
          {addMutation.isPending ? "Importing..." : "Import"}
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Dialog
// ---------------------------------------------------------------------------

export function AddMoleculesDialog({ collectionId, open, onOpenChange }: AddMoleculesDialogProps) {
  const [lastResult, setLastResult] = useState<MembershipResult | null>(null);

  function handleClose(v: boolean) {
    if (!v) setLastResult(null);
    onOpenChange(v);
  }

  const handleResult = useCallback((result: MembershipResult) => {
    setLastResult(result);
  }, []);

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Add Molecules</DialogTitle>
          <DialogDescription>
            Search, paste identifiers, or import from CSV to add molecules to this collection.
          </DialogDescription>
        </DialogHeader>

        {lastResult && <MembershipResultDisplay result={lastResult} />}

        <Tabs defaultValue="search" className="w-full">
          <TabsList>
            <TabsTrigger value="search">Search</TabsTrigger>
            <TabsTrigger value="paste">Paste</TabsTrigger>
            <TabsTrigger value="csv">CSV Import</TabsTrigger>
          </TabsList>

          <TabsContent value="search">
            <SearchTab collectionId={collectionId} onResult={handleResult} />
          </TabsContent>

          <TabsContent value="paste">
            <PasteTab collectionId={collectionId} onResult={handleResult} />
          </TabsContent>

          <TabsContent value="csv">
            <CsvTab collectionId={collectionId} onResult={handleResult} />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
