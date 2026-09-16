"use client";

import { useOrganizations } from "@/features/workspace-config/hooks/use-organizations";
import { SearchableSelect } from "@/shared/components/searchable-select";
import { Badge } from "@/shared/components/ui/badge";
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
import { RadioGroup, RadioGroupItem } from "@/shared/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";
import { Textarea } from "@/shared/components/ui/textarea";
import { useMemberNames } from "@/shared/hooks/use-workspace-members";
import { saveText } from "@/shared/lib/api/download";
import type { ShipmentDirection, ShipmentItemType } from "@/shared/lib/api/model";
import { parseCsv } from "@/shared/lib/parse-csv";
import { formatStatusLabel } from "@/shared/lib/status-variants";
import { AlertTriangle, CheckCircle2, Download, Plus, Trash2, Upload, XCircle } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { useBatchesByMolecule } from "../hooks/use-batches";
import { LoanStatus, useLoans } from "../hooks/use-plate-loans";
import { useSamplesByBatch } from "../hooks/use-samples";
import {
  useCreateShipment,
  usePreviewShipmentImport,
  useResolveShipmentItems,
} from "../hooks/use-shipments";
import { loanTitle } from "../lib/loan-summary";
import type {
  ImportFieldCorrection,
  ImportResolvedRow,
  ResolvedItem,
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

/** A barcode the server resolved, staged in the dialog. Plates ship whole — no amount. */
interface ResolvedRow {
  item_type: ShipmentItemType;
  item_id: string;
  barcode: string;
  label: string | null;
  amount_value: number;
  amount_unit: string;
}

const isBlank = (it: ItemRowState) => !it._moleculeId && !it._batchId && !it.sample_id;

function toRequestItem(r: ResolvedRow): ShipmentItemInput {
  return r.item_type === "plate"
    ? { item_type: "plate", item_id: r.item_id }
    : {
        item_type: "sample",
        item_id: r.item_id,
        amount_value: r.amount_value,
        amount_unit: r.amount_unit,
      };
}

// ---------------------------------------------------------------------------
// CSV helpers
// ---------------------------------------------------------------------------

function downloadTemplate() {
  const header = "compound,batch,sample,amount";
  const row1 = "CC-000001,B-001,SMP-001,5mg";
  const row2 = "Aspirin,B-002,SMP-005,2.5 g";
  saveText([header, row1, row2].join("\n"), "shipment-template.csv");
}

/**
 * Parse shipment CSV (header: `compound,batch,sample,amount`) into rows. Uses
 * the shared PapaParse-based parser so quoted/comma-containing fields (e.g. a
 * compound name with a comma) round-trip correctly.
 */
async function parseCSV(
  text: string,
): Promise<Array<{ compound: string; batch: string; sample: string; amount: string }>> {
  const parsed = await parseCsv(text);
  if (parsed.kind !== "ok") return [];
  return parsed.rows.map((row) => ({
    compound: row.compound ?? "",
    batch: row.batch ?? "",
    sample: row.sample ?? "",
    amount: row.amount ?? "",
  }));
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

function UnitSelect({
  value,
  onValueChange,
}: { value: string; onValueChange: (v: string) => void }) {
  return (
    <Select value={value} onValueChange={onValueChange}>
      <SelectTrigger className="w-20">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="mg">mg</SelectItem>
        <SelectItem value="g">g</SelectItem>
        <SelectItem value="mL">mL</SelectItem>
      </SelectContent>
    </Select>
  );
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

        <div className="grid gap-1">
          <Label className="text-xs">Unit</Label>
          <UnitSelect value={item.amount_unit} onValueChange={(v) => onUpdate("amount_unit", v)} />
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
  const resolveMutation = useResolveShipmentItems();
  const { data: orgs } = useOrganizations();
  const { data: loans } = useLoans({ status: LoanStatus.open }, { enabled: open });
  const memberName = useMemberNames();
  const loanOptions = useMemo(
    () =>
      (loans ?? []).map((l) => ({ value: l.id, label: loanTitle(l, memberName(l.requested_by)) })),
    [loans, memberName],
  );

  // Shared fields
  const [direction, setDirection] = useState<ShipmentDirection>("outbound");
  const [destinationOrgId, setDestinationOrgId] = useState("");
  const [loanId, setLoanId] = useState<string | null>(null);
  const [carrier, setCarrier] = useState("");
  const [expectedArrivalDate, setExpectedArrivalDate] = useState("");
  const [shippingConditions, setShippingConditions] = useState("");
  const [notes, setNotes] = useState("");

  // Manual tab — barcode box + cascade rows
  const [barcodes, setBarcodes] = useState("");
  const [resolved, setResolved] = useState<ResolvedRow[]>([]);
  const [unresolved, setUnresolved] = useState<ResolvedItem[]>([]);
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
    setDirection("outbound");
    setDestinationOrgId("");
    setLoanId(null);
    setCarrier("");
    setExpectedArrivalDate("");
    setShippingConditions("");
    setNotes("");
    setBarcodes("");
    setResolved([]);
    setUnresolved([]);
    setItems([{ ...EMPTY_ITEM }]);
    setCsvText("");
    setPreviewRows(null);
    setPreviewSummary(null);
  }

  function handleClose(v: boolean) {
    if (!v) resetForm();
    onOpenChange(v);
  }

  /** Header fields shared by both submit paths. */
  const header = () => ({
    destination_org_id: destinationOrgId.trim(),
    direction,
    loan_id: loanId,
    carrier: carrier.trim() || null,
    expected_arrival_date: expectedArrivalDate || null,
    shipping_conditions: shippingConditions.trim() || null,
    notes: notes.trim() || null,
  });

  // --- Barcode box ---

  function handleResolve() {
    const codes = barcodes
      .split(/\r?\n/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (codes.length === 0) return;
    resolveMutation.mutate(codes, {
      onSuccess: (rows) => {
        setResolved((prev) => {
          const seen = new Set(prev.map((r) => r.item_id));
          const next = [...prev];
          for (const r of rows) {
            if (!r.item_type || !r.item_id || seen.has(r.item_id)) continue;
            seen.add(r.item_id);
            next.push({
              item_type: r.item_type,
              item_id: r.item_id,
              barcode: r.barcode,
              label: r.label ?? null,
              amount_value: 0,
              amount_unit: "mg",
            });
          }
          return next;
        });
        const failed = rows.filter((r) => r.error);
        setUnresolved(failed);
        // Keep only the failures in the box so a typo can be fixed and re-resolved.
        setBarcodes(failed.map((r) => r.barcode).join("\n"));
      },
    });
  }

  function updateResolved(index: number, patch: Partial<ResolvedRow>) {
    setResolved((prev) => prev.map((r, i) => (i === index ? { ...r, ...patch } : r)));
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

  // Untouched cascade rows don't count — a barcode-only shipment is valid.
  const cascade = items.filter((it) => !isBlank(it));
  const manualValid =
    destinationOrgId.trim().length > 0 &&
    cascade.length + resolved.length > 0 &&
    cascade.every(
      (it) => it.sample_id.trim().length > 0 && it.amount_value > 0 && it.amount_unit.length > 0,
    ) &&
    resolved.every((r) => r.item_type === "plate" || r.amount_value > 0);

  function handleManualSubmit() {
    const apiItems: ShipmentItemInput[] = [
      ...cascade.map((it) => ({
        item_type: "sample" as const,
        item_id: it.sample_id,
        amount_value: it.amount_value,
        amount_unit: it.amount_unit,
      })),
      ...resolved.map(toRequestItem),
    ];
    mutation.mutate({ ...header(), items: apiItems }, { onSuccess: () => handleClose(false) });
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

  async function handleValidate() {
    const parsed = await parseCSV(csvText);
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
        item_type: "sample" as const,
        item_id: r.sample_id!,
        amount_value: r.amount_value!,
        amount_unit: r.amount_unit!,
      }));

    mutation.mutate({ ...header(), items: apiItems }, { onSuccess: () => handleClose(false) });
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
            Pick the direction and organization, then add plates or samples by barcode or by
            compound → batch → sample.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          {/* Shared fields: direction, organization, loan, carrier, conditions */}
          <div className="grid gap-2">
            <Label>Direction</Label>
            <RadioGroup
              value={direction}
              onValueChange={(v) => setDirection(v as ShipmentDirection)}
              className="flex gap-6"
            >
              <div className="flex items-center gap-2">
                <RadioGroupItem value="outbound" id="ship-dir-out" />
                <Label htmlFor="ship-dir-out" className="font-normal">
                  Outbound
                </Label>
              </div>
              <div className="flex items-center gap-2">
                <RadioGroupItem value="inbound" id="ship-dir-in" />
                <Label htmlFor="ship-dir-in" className="font-normal">
                  Inbound
                </Label>
              </div>
            </RadioGroup>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="ship-org">
                {direction === "inbound" ? "From Organization" : "Destination Organization"}{" "}
                <span className="text-destructive">*</span>
              </Label>
              <Select value={destinationOrgId} onValueChange={setDestinationOrgId}>
                <SelectTrigger id="ship-org">
                  <SelectValue placeholder="Select organization" />
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
            <div className="grid gap-2">
              <Label>Loan</Label>
              <SearchableSelect
                options={loanOptions}
                value={loanId}
                onValueChange={setLoanId}
                placeholder="No loan"
                searchPlaceholder="Search open loans..."
                emptyMessage="No open loans."
              />
            </div>
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
              <div className="grid gap-3 pt-2">
                {/* Barcode box */}
                <div className="grid gap-2 rounded-md border p-3">
                  <Label htmlFor="ship-barcodes">Barcodes</Label>
                  <Textarea
                    id="ship-barcodes"
                    placeholder="Plates or samples, one per line"
                    rows={3}
                    className="font-mono text-xs"
                    value={barcodes}
                    onChange={(e) => setBarcodes(e.target.value)}
                  />
                  <div className="flex items-center gap-3">
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      disabled={barcodes.trim().length === 0 || resolveMutation.isPending}
                      onClick={handleResolve}
                    >
                      {resolveMutation.isPending ? "Resolving..." : "Resolve"}
                    </Button>
                    <span className="text-xs text-muted-foreground">
                      Plates ship whole; samples need an amount.
                    </span>
                  </div>
                  {unresolved.length > 0 ? (
                    <ul className="text-sm">
                      {unresolved.map((u) => (
                        <li key={u.barcode} className="text-destructive">
                          {u.barcode} — {u.error}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {resolved.length > 0 ? (
                    <ul data-testid="resolved-items" className="divide-y rounded-md border">
                      {resolved.map((r, i) => (
                        <li
                          key={r.item_id}
                          className="flex flex-wrap items-center gap-3 px-3 py-2 text-sm"
                        >
                          <Badge variant="outline">{formatStatusLabel(r.item_type)}</Badge>
                          <span className="font-mono">{r.barcode}</span>
                          <span className="text-muted-foreground">{r.label}</span>
                          <span className="ml-auto flex items-center gap-2">
                            {r.item_type === "sample" ? (
                              <>
                                <Input
                                  type="number"
                                  placeholder="0.0"
                                  min={0}
                                  className="w-24"
                                  aria-label={`Amount for ${r.barcode}`}
                                  value={r.amount_value || ""}
                                  onChange={(e) =>
                                    updateResolved(i, {
                                      amount_value: Number.parseFloat(e.target.value) || 0,
                                    })
                                  }
                                />
                                <UnitSelect
                                  value={r.amount_unit}
                                  onValueChange={(v) => updateResolved(i, { amount_unit: v })}
                                />
                              </>
                            ) : null}
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7 text-destructive"
                              aria-label={`Remove ${r.barcode}`}
                              onClick={() => setResolved((prev) => prev.filter((_, j) => j !== i))}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>

                {/* Cascade rows */}
                <div className="flex items-center justify-between">
                  <Label>By compound</Label>
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
                  onClick={() => void handleValidate()}
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
