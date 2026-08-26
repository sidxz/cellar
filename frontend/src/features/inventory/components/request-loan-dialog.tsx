"use client";

import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
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
import { useOrgs } from "@/shared/hooks/use-orgs";
import { saveText } from "@/shared/lib/api/download";
import type { RequestLoanBody } from "@/shared/lib/api/model";
import { parseCsvRows } from "@/shared/lib/parse-csv";
import { Download } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import type { PlateGroupNode } from "../hooks/use-plate-groups";
import { usePlateGroupTree } from "../hooks/use-plate-groups";
import { useRequestLoan } from "../hooks/use-plate-loans";

type Mode = "group" | "paste" | "csv";

/** Sentinel for "no borrower selected" — self-checkout onto the caller's own org. */
const MY_ORG = "__mine__";

const TEMPLATE = "Barcode\n005261\n003251\n";

/** One barcode per non-empty line. */
function splitBarcodes(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/** First CSV column as barcodes, skipping a leading "Barcode" header row. */
export function csvFirstColumn(text: string): string[] {
  const rows = parseCsvRows(text);
  const start = rows[0]?.[0]?.toLowerCase() === "barcode" ? 1 : 0;
  return rows
    .slice(start)
    .map((r) => r[0] ?? "")
    .filter(Boolean);
}

interface GroupOption {
  id: string;
  label: string;
}

function flattenGroups(nodes: PlateGroupNode[], depth: number, out: GroupOption[]): void {
  for (const n of nodes) {
    out.push({
      id: n.id,
      label: `${" ".repeat(depth * 3)}${n.name} (${n.plate_count})`,
    });
    flattenGroups(n.children ?? [], depth + 1, out);
  }
}

export interface RequestLoanDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Borrower org whose plate-group tree is offered in group mode. */
  orgId: string | undefined;
  /** Group to preselect in "From group" mode, e.g. opened from a tree card. */
  initialGroupId?: string;
  /** Barcodes to pre-fill in "Paste barcodes" mode (opens in that mode when non-empty).
   *  Pass a stable reference — an inline literal re-runs the reset effect every render. */
  initialBarcodes?: string[];
}

export function RequestLoanDialog({
  open,
  onOpenChange,
  orgId,
  initialGroupId,
  initialBarcodes,
}: RequestLoanDialogProps) {
  const [mode, setMode] = useState<Mode>("group");
  const [groupId, setGroupId] = useState("");
  const [paste, setPaste] = useState("");
  const [csvBarcodes, setCsvBarcodes] = useState<string[]>([]);
  const [csvName, setCsvName] = useState("");
  const [borrowerOrgId, setBorrowerOrgId] = useState<string>(MY_ORG);
  const [dueDate, setDueDate] = useState("");
  const [notes, setNotes] = useState("");
  const request = useRequestLoan();
  const router = useRouter();

  const { data: orgs } = useOrgs();
  const borrowerOptions = useMemo(() => (orgs ?? []).filter((o) => o.id !== orgId), [orgs, orgId]);
  const isLending = borrowerOrgId !== MY_ORG;

  const { data: tree } = usePlateGroupTree(orgId, { enabled: open && !!orgId });

  useEffect(() => {
    if (!open) return;
    const preset = initialBarcodes ?? [];
    setMode(preset.length > 0 ? "paste" : "group");
    setGroupId(initialGroupId ?? "");
    setPaste(preset.join("\n"));
    setCsvBarcodes([]);
    setCsvName("");
    setBorrowerOrgId(MY_ORG);
    setDueDate("");
    setNotes("");
  }, [open, initialGroupId, initialBarcodes]);

  const groupOptions = useMemo(() => {
    const out: GroupOption[] = [];
    if (tree) flattenGroups(tree.roots, 0, out);
    return out;
  }, [tree]);

  const barcodes = mode === "paste" ? splitBarcodes(paste) : csvBarcodes;
  const hasInput = mode === "group" ? groupId !== "" : barcodes.length > 0;

  const handleFile = (file: File | undefined) => {
    if (!file) return;
    setCsvName(file.name);
    const reader = new FileReader();
    reader.onload = () => setCsvBarcodes(csvFirstColumn(String(reader.result ?? "")));
    reader.readAsText(file);
  };

  const handleSubmit = () => {
    const body: RequestLoanBody = {};
    if (mode === "group") body.group_id = groupId;
    else body.barcodes = barcodes;
    if (isLending) body.borrower_org_id = borrowerOrgId;
    if (dueDate) body.due_date = dueDate;
    if (notes.trim()) body.notes = notes.trim();
    request.mutate(body, {
      onSuccess: (loan) => {
        onOpenChange(false);
        router.push(`/inventory/loans/${loan.id}`);
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Request loan</DialogTitle>
        </DialogHeader>

        <Tabs value={mode} onValueChange={(v) => setMode(v as Mode)}>
          <TabsList>
            <TabsTrigger value="group">From group</TabsTrigger>
            <TabsTrigger value="paste">Paste barcodes</TabsTrigger>
            <TabsTrigger value="csv">CSV</TabsTrigger>
          </TabsList>

          <TabsContent value="group" className="mt-3">
            <Select value={groupId} onValueChange={setGroupId}>
              <SelectTrigger aria-label="Plate group">
                <SelectValue placeholder={orgId ? "Select a group" : "No organization"} />
              </SelectTrigger>
              <SelectContent>
                {groupOptions.map((o) => (
                  <SelectItem key={o.id} value={o.id}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="mt-2 text-xs text-muted-foreground">
              Requests every plate directly in the selected group — sub-groups are loaned
              separately.
            </p>
          </TabsContent>

          <TabsContent value="paste" className="mt-3">
            <Textarea
              aria-label="Barcodes"
              placeholder="One barcode per line"
              rows={6}
              value={paste}
              onChange={(e) => setPaste(e.target.value)}
            />
          </TabsContent>

          <TabsContent value="csv" className="mt-3 flex flex-col gap-2">
            <div className="flex items-center justify-between gap-2">
              <Label htmlFor="loan-csv">CSV file</Label>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => saveText(TEMPLATE, "loan_request_template.csv")}
              >
                <Download className="mr-2 h-4 w-4" />
                Download template
              </Button>
            </div>
            <Input
              id="loan-csv"
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => handleFile(e.target.files?.[0])}
            />
            {csvName ? (
              <p className="text-xs text-muted-foreground">
                {csvName}: {csvBarcodes.length} barcode(s)
              </p>
            ) : null}
          </TabsContent>
        </Tabs>

        <div className="flex flex-col gap-2">
          <Label htmlFor="loan-borrower">Borrower organization</Label>
          <Select value={borrowerOrgId} onValueChange={setBorrowerOrgId}>
            <SelectTrigger id="loan-borrower">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={MY_ORG}>My organization (self-checkout)</SelectItem>
              {borrowerOptions.map((o) => (
                <SelectItem key={o.id} value={o.id}>
                  {o.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="loan-due">Due date (optional)</Label>
          <Input
            id="loan-due"
            type="date"
            value={dueDate}
            onChange={(e) => setDueDate(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="loan-notes">Notes (optional)</Label>
          <Textarea
            id="loan-notes"
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={request.isPending}
          >
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={request.isPending || !hasInput}>
            {isLending ? "Lend" : "Request loan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
