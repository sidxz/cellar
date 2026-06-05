"use client";

import { useOrganizations } from "@/features/workspace-config/hooks/use-organizations";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Input } from "@/shared/components/ui/input";
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
import { AlertTriangle, CheckCircle2, Download, Plus, Trash2, Upload, XCircle } from "lucide-react";
import { useRef, useState } from "react";
import { useBatchesByMolecule } from "../hooks/use-batches";
import { useSamplesByBatch } from "../hooks/use-samples";
import { useCreateShipment, usePreviewShipmentImport } from "../hooks/use-shipments";
import type {
  ImportFieldCorrection,
  ImportResolvedRow,
  ShipmentItemInput,
} from "../types/shipment";
import { MoleculeSelector } from "./molecule-selector";

interface CreateShipmentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** One item row with cascading selectors: compound -> batch -> sample */
interface ItemRowState {
  _moleculeId: string | null;
  _batchId: string;
  sample_id: string;
  amount_value: number;
  amount_unit: string;
}

const EMPTY_ITEM: ItemRowState = {
  _moleculeId: null,
  _batchId: "",
  sample_id: "",
  amount_value: 0,
  amount_unit: "mg",
};

// ---------------------------------------------------------------------------
// CSV helpers
// ---------------------------------------------------------------------------

function downloadTemplate() {
  const header = "compound,batch,sample,amount";
  const row1 = "CC-000001,B-001,SMP-001,5mg";
  const row2 = "Aspirin,B-002,SMP-005,2.5 g";
  const csv = [header, row1, row2].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "shipment-template.csv";
  a.click();
  URL.revokeObjectURL(url);
}

function parseCSV(
  text: string,
): Array<{ compound: string; batch: string; sample: string; amount: string }> {
  const lines = text
    .trim()
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.length > 0);
  if (lines.length < 2) return []; // Need header + at least 1 row

  // Skip header row
  return lines.slice(1).map((line) => {
    const cols = line.split(",").map((c) => c.trim());
    return {
      compound: cols[0] || "",
      batch: cols[1] || "",
      sample: cols[2] || "",
      amount: cols[3] || "",
    };
  });
}

// ---------------------------------------------------------------------------
// Preview cell — highlights corrections
// ---------------------------------------------------------------------------

function PreviewCell({
  original,
  corrected,
  hasCorrection,
}: {
  original: string;
  corrected?: string;
  hasCorrection: boolean;
}) {
  if (hasCorrection && corrected) {
    return (
      <td className="px-3 py-2 bg-yellow-500/10">
        <span className="font-medium">{corrected}</span>
        <span className="ml-2 text-xs text-muted-foreground line-through">{original}</span>
      </td>
    );
  }
  return <td className="px-3 py-2">{original}</td>;
}

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case "valid":
      return <CheckCircle2 className="h-4 w-4 text-success" />;
    case "corrected":
      return <AlertTriangle className="h-4 w-4 text-yellow-500" />;
    case "error":
      return <XCircle className="h-4 w-4 text-destructive" />;
    default:
      return null;
  }
}

// ---------------------------------------------------------------------------
// Cascading item row: Compound -> Batch -> Sample
// ---------------------------------------------------------------------------

function ShipmentItemRow({
  item,
  index,
  canRemove,
  onUpdate,
  onRemove,
}: {
  item: ItemRowState;
  index: number;
  canRemove: boolean;
  onUpdate: <K extends keyof ItemRowState>(key: K, value: ItemRowState[K]) => void;
  onRemove: () => void;
}) {
  const { data: batches, isLoading: batchesLoading } = useBatchesByMolecule(
    item._moleculeId ?? undefined,
  );
  const { data: samples, isLoading: samplesLoading } = useSamplesByBatch(
    item._batchId || undefined,
  );

  return (
    <div className="rounded-md border p-3 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">Item {index + 1}</span>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-destructive"
          disabled={!canRemove}
          onClick={onRemove}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>

      {/* Row 1: Compound -> Batch */}
      <div className="grid grid-cols-2 gap-3">
        <div className="grid gap-1">
          <Label className="text-xs">
            Compound <span className="text-destructive">*</span>
          </Label>
          <MoleculeSelector
            selectedId={item._moleculeId}
            onSelect={(id) => {
              onUpdate("_moleculeId", id);
              onUpdate("_batchId", "");
              onUpdate("sample_id", "");
            }}
          />
        </div>

        <div className="grid gap-1">
          <Label className="text-xs">
            Batch <span className="text-destructive">*</span>
          </Label>
          {item._moleculeId ? (
            <Select
              value={item._batchId}
              onValueChange={(val) => {
                onUpdate("_batchId", val);
                onUpdate("sample_id", "");
              }}
              disabled={batchesLoading}
            >
              <SelectTrigger>
                <SelectValue
                  placeholder={
                    batchesLoading
                      ? "Loading batches..."
                      : batches && batches.length === 0
                        ? "No batches found"
                        : "Select batch"
                  }
                />
              </SelectTrigger>
              <SelectContent>
                {batches?.map((b) => (
                  <SelectItem key={b.id} value={b.id}>
                    {b.batch_number}
                    {b.purity ? ` (${b.purity}% pure)` : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <Select disabled>
              <SelectTrigger>
                <SelectValue placeholder="Select compound first" />
              </SelectTrigger>
              <SelectContent />
            </Select>
          )}
        </div>
      </div>

      {/* Row 2: Sample -> Amount */}
      <div className="grid grid-cols-[1fr_auto_auto] gap-3 items-end">
        <div className="grid gap-1">
          <Label className="text-xs">
            Sample <span className="text-destructive">*</span>
          </Label>
          {item._batchId && samples && samples.length > 0 ? (
            <Select
              value={item.sample_id}
              onValueChange={(val) => onUpdate("sample_id", val)}
              disabled={samplesLoading}
            >
              <SelectTrigger>
                <SelectValue
                  placeholder={samplesLoading ? "Loading samples..." : "Select sample"}
                />
              </SelectTrigger>
              <SelectContent>
                {samples.map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.barcode} -- {s.amount_value} {s.amount_unit} available
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <Select disabled>
              <SelectTrigger>
                <SelectValue
                  placeholder={
                    !item._batchId
                      ? "Select batch first"
                      : samplesLoading
                        ? "Loading..."
                        : "No samples in this batch"
                  }
                />
              </SelectTrigger>
              <SelectContent />
            </Select>
          )}
        </div>

        <div className="grid gap-1 w-24">
          <Label className="text-xs">
            Amount <span className="text-destructive">*</span>
          </Label>
          <Input
            type="number"
            placeholder="0.0"
            min={0}
            value={item.amount_value || ""}
            onChange={(e) => onUpdate("amount_value", Number.parseFloat(e.target.value) || 0)}
          />
        </div>

        <div className="grid gap-1 w-20">
          <Label className="text-xs">Unit</Label>
          <Select value={item.amount_unit} onValueChange={(val) => onUpdate("amount_unit", val)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="mg">mg</SelectItem>
              <SelectItem value="g">g</SelectItem>
              <SelectItem value="mL">mL</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main dialog
// ---------------------------------------------------------------------------

export function CreateShipmentDialog({ open, onOpenChange }: CreateShipmentDialogProps) {
  const mutation = useCreateShipment();
  const previewMutation = usePreviewShipmentImport();
  const { data: orgs } = useOrganizations();

  // Shared fields
  const [destinationOrgId, setDestinationOrgId] = useState("");
  const [carrier, setCarrier] = useState("");
  const [expectedArrivalDate, setExpectedArrivalDate] = useState("");
  const [shippingConditions, setShippingConditions] = useState("");
  const [notes, setNotes] = useState("");

  // Manual tab
  const [items, setItems] = useState<ItemRowState[]>([{ ...EMPTY_ITEM }]);

  // CSV tab
  const [csvText, setCsvText] = useState("");
  const [previewRows, setPreviewRows] = useState<ImportResolvedRow[] | null>(null);
  const [previewSummary, setPreviewSummary] = useState<{
    total: number;
    valid: number;
    corrected: number;
    errors: number;
  } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function resetForm() {
    setDestinationOrgId("");
    setCarrier("");
    setExpectedArrivalDate("");
    setShippingConditions("");
    setNotes("");
    setItems([{ ...EMPTY_ITEM }]);
    setCsvText("");
    setPreviewRows(null);
    setPreviewSummary(null);
  }

  function handleClose(v: boolean) {
    if (!v) resetForm();
    onOpenChange(v);
  }

  // --- Manual tab helpers ---

  function addItem() {
    setItems((prev) => [...prev, { ...EMPTY_ITEM }]);
  }

  function removeItem(index: number) {
    setItems((prev) => prev.filter((_, i) => i !== index));
  }

  function updateItem<K extends keyof ItemRowState>(index: number, key: K, value: ItemRowState[K]) {
    setItems((prev) => prev.map((item, i) => (i === index ? { ...item, [key]: value } : item)));
  }

  const manualValid =
    destinationOrgId.trim().length > 0 &&
    items.length > 0 &&
    items.every(
      (it) => it.sample_id.trim().length > 0 && it.amount_value > 0 && it.amount_unit.length > 0,
    );

  function handleManualSubmit() {
    const apiItems: ShipmentItemInput[] = items.map((it) => ({
      sample_id: it.sample_id,
      amount_value: it.amount_value,
      amount_unit: it.amount_unit,
    }));
    mutation.mutate(
      {
        destination_org_id: destinationOrgId.trim(),
        carrier: carrier.trim() || null,
        expected_arrival_date: expectedArrivalDate || null,
        shipping_conditions: shippingConditions.trim() || null,
        notes: notes.trim() || null,
        items: apiItems,
      },
      { onSuccess: () => handleClose(false) },
    );
  }

  // --- CSV tab helpers ---

  function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result as string;
      setCsvText(text);
      setPreviewRows(null);
      setPreviewSummary(null);
    };
    reader.readAsText(file);
    // Reset input so same file can be re-selected
    e.target.value = "";
  }

  function handleValidate() {
    const parsed = parseCSV(csvText);
    if (parsed.length === 0) return;

    previewMutation.mutate(parsed, {
      onSuccess: (data) => {
        setPreviewRows(data.rows);
        setPreviewSummary({
          total: data.total,
          valid: data.valid_count,
          corrected: data.corrected_count,
          errors: data.error_count,
        });
      },
    });
  }

  const csvValid =
    destinationOrgId.trim().length > 0 &&
    previewRows != null &&
    previewRows.length > 0 &&
    previewSummary != null &&
    previewSummary.errors === 0;

  function handleCsvSubmit() {
    if (!previewRows || !csvValid) return;

    const apiItems: ShipmentItemInput[] = previewRows
      .filter((r) => r.status !== "error" && r.sample_id && r.amount_value && r.amount_unit)
      .map((r) => ({
        sample_id: r.sample_id!,
        amount_value: r.amount_value!,
        amount_unit: r.amount_unit!,
      }));

    mutation.mutate(
      {
        destination_org_id: destinationOrgId.trim(),
        carrier: carrier.trim() || null,
        expected_arrival_date: expectedArrivalDate || null,
        shipping_conditions: shippingConditions.trim() || null,
        notes: notes.trim() || null,
        items: apiItems,
      },
      { onSuccess: () => handleClose(false) },
    );
  }

  // --- Helper: find correction for a field ---
  function getCorrection(
    corrections: ImportFieldCorrection[],
    fieldName: string,
  ): ImportFieldCorrection | undefined {
    return corrections.find((c) => c.field === fieldName);
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>New Shipment</DialogTitle>
          <DialogDescription>
            Select compounds, then pick batches and samples to ship.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          {/* Shared fields: destination, carrier, conditions */}
          <div className="grid gap-2">
            <Label>
              Destination Organization <span className="text-destructive">*</span>
            </Label>
            <Select value={destinationOrgId} onValueChange={setDestinationOrgId}>
              <SelectTrigger>
                <SelectValue placeholder="Select destination organization" />
              </SelectTrigger>
              <SelectContent>
                {orgs?.map((o) => (
                  <SelectItem key={o.id} value={o.id}>
                    {o.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Carrier</Label>
              <Input
                placeholder="e.g. FedEx, DHL"
                value={carrier}
                onChange={(e) => setCarrier(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label>Expected Arrival</Label>
              <Input
                type="date"
                value={expectedArrivalDate}
                onChange={(e) => setExpectedArrivalDate(e.target.value)}
              />
            </div>
          </div>

          <div className="grid gap-2">
            <Label>Shipping Conditions</Label>
            <Input
              placeholder="e.g. Keep refrigerated at 2-8 C"
              value={shippingConditions}
              onChange={(e) => setShippingConditions(e.target.value)}
            />
          </div>

          {/* Tabbed item selection */}
          <Tabs defaultValue="manual" className="w-full">
            <TabsList>
              <TabsTrigger value="manual">Manual</TabsTrigger>
              <TabsTrigger value="csv">CSV Import</TabsTrigger>
            </TabsList>

            {/* ---- Manual tab ---- */}
            <TabsContent value="manual">
              <div className="grid gap-2 pt-2">
                <div className="flex items-center justify-between">
                  <Label>
                    Samples to Ship <span className="text-destructive">*</span>
                  </Label>
                  <Button type="button" variant="outline" size="sm" onClick={addItem}>
                    <Plus className="mr-1 h-3 w-3" />
                    Add Another Compound
                  </Button>
                </div>

                <div className="space-y-3">
                  {items.map((item, index) => (
                    <ShipmentItemRow
                      key={index}
                      item={item}
                      index={index}
                      canRemove={items.length > 1}
                      onUpdate={(key, value) => updateItem(index, key, value)}
                      onRemove={() => removeItem(index)}
                    />
                  ))}
                </div>
              </div>

              <DialogFooter className="mt-4">
                <Button variant="outline" onClick={() => handleClose(false)}>
                  Cancel
                </Button>
                <Button onClick={handleManualSubmit} disabled={!manualValid || mutation.isPending}>
                  {mutation.isPending ? "Creating..." : "Create Shipment"}
                </Button>
              </DialogFooter>
            </TabsContent>

            {/* ---- CSV Import tab ---- */}
            <TabsContent value="csv">
              <div className="grid gap-4 pt-2">
                {/* Template + Upload */}
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
                </div>

                {/* CSV text area */}
                <div className="grid gap-1">
                  <Label className="text-xs">Paste CSV or upload a file above</Label>
                  <Textarea
                    placeholder={"compound,batch,sample,amount\nCC-000001,B-001,SMP-001,5mg"}
                    rows={5}
                    className="font-mono text-xs"
                    value={csvText}
                    onChange={(e) => {
                      setCsvText(e.target.value);
                      setPreviewRows(null);
                      setPreviewSummary(null);
                    }}
                  />
                </div>

                {/* Validate button */}
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  disabled={csvText.trim().length === 0 || previewMutation.isPending}
                  onClick={handleValidate}
                >
                  {previewMutation.isPending ? "Validating..." : "Validate & Preview"}
                </Button>

                {/* Preview results */}
                {previewRows && previewSummary && (
                  <div className="space-y-3">
                    {/* Summary bar */}
                    <div className="flex items-center gap-4 text-sm">
                      <span className="font-medium">{previewSummary.total} items:</span>
                      <span className="text-success">{previewSummary.valid} valid</span>
                      <span className="text-yellow-500">{previewSummary.corrected} corrected</span>
                      <span className="text-destructive">{previewSummary.errors} errors</span>
                    </div>

                    {/* Preview table */}
                    <div className="overflow-x-auto rounded-md border">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b bg-muted/50">
                            <th className="px-3 py-2 text-left w-8">#</th>
                            <th className="px-3 py-2 text-left">Compound</th>
                            <th className="px-3 py-2 text-left">Batch</th>
                            <th className="px-3 py-2 text-left">Sample</th>
                            <th className="px-3 py-2 text-left">Amount</th>
                            <th className="px-3 py-2 text-center w-10">Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {previewRows.map((row) => {
                            const compoundCorr = getCorrection(row.corrections, "compound");
                            const batchCorr = getCorrection(row.corrections, "batch");
                            const sampleCorr = getCorrection(row.corrections, "sample");
                            const amountCorr = getCorrection(row.corrections, "amount");

                            return (
                              <tr
                                key={row.row_number}
                                className={row.status === "error" ? "bg-destructive/5" : ""}
                              >
                                <td className="px-3 py-2 text-muted-foreground">
                                  {row.row_number}
                                </td>
                                <PreviewCell
                                  original={row.original.compound}
                                  corrected={
                                    compoundCorr ? (row.compound_display ?? undefined) : undefined
                                  }
                                  hasCorrection={!!compoundCorr}
                                />
                                <PreviewCell
                                  original={row.original.batch}
                                  corrected={
                                    batchCorr ? (row.batch_display ?? undefined) : undefined
                                  }
                                  hasCorrection={!!batchCorr}
                                />
                                <PreviewCell
                                  original={row.original.sample}
                                  corrected={
                                    sampleCorr ? (row.sample_display ?? undefined) : undefined
                                  }
                                  hasCorrection={!!sampleCorr}
                                />
                                <PreviewCell
                                  original={row.original.amount}
                                  corrected={amountCorr?.corrected}
                                  hasCorrection={!!amountCorr}
                                />
                                <td className="px-3 py-2 text-center">
                                  <StatusIcon status={row.status} />
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>

                    {/* Error details */}
                    {previewRows.some((r) => r.errors.length > 0) && (
                      <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm space-y-1">
                        {previewRows
                          .filter((r) => r.errors.length > 0)
                          .map((r) => (
                            <div key={r.row_number}>
                              <span className="font-medium text-destructive">
                                Row {r.row_number}:
                              </span>{" "}
                              {r.errors.join("; ")}
                            </div>
                          ))}
                      </div>
                    )}
                  </div>
                )}
              </div>

              <DialogFooter className="mt-4">
                <Button variant="outline" onClick={() => handleClose(false)}>
                  Cancel
                </Button>
                <Button onClick={handleCsvSubmit} disabled={!csvValid || mutation.isPending}>
                  {mutation.isPending ? "Creating..." : "Create Shipment"}
                </Button>
              </DialogFooter>
            </TabsContent>
          </Tabs>

          {/* Notes — shared */}
          <div className="grid gap-2">
            <Label>Notes</Label>
            <Textarea
              placeholder="Additional notes..."
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
