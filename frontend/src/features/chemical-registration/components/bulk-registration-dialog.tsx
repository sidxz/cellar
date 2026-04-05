"use client";

import { useCallback, useState } from "react";
import { Download, FileUp, Upload, CheckCircle2, XCircle, AlertCircle } from "lucide-react";
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
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { useOrganizations } from "@/features/workspace-config/hooks/use-organizations";
import {
  useBulkRegistration,
  type BulkRegistrationResponse,
} from "../hooks/use-bulk-registration";

function downloadCsvTemplate() {
  // Columns match the backend TabularParser aliases exactly.
  // Multiple identifier columns supported — each compound can carry
  // CAS, vendor ID, ChEMBL, PubChem, and custom IDs in the same row.
  // All ID columns are optional; include only the ones you have.
  const header = "name,smiles,molecule_type,cas_number,vendor_id,chembl_id,pubchem_cid,custom_id,custom_id_1,custom_id_2";
  const example1 = "Aspirin,CC(=O)Oc1ccccc1C(O)=O,small_molecule,50-78-2,VENDOR-001,CHEMBL25,2244,,,";
  const example2 = "Caffeine,Cn1c(=O)c2c(ncn2C)n(C)c1=O,small_molecule,58-08-2,,CHEMBL113,2519,,,";
  const example3 = "Undisclosed Partner Compound,,small_molecule,,PARTNER-042,,,PROJECT-X-017,PLATE-042,LOT-2026-A";
  const csv = [header, example1, example2, example3].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "bulk_registration_template.csv";
  a.click();
  URL.revokeObjectURL(url);
}

interface BulkRegistrationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function BulkRegistrationDialog({
  open,
  onOpenChange,
}: BulkRegistrationDialogProps) {
  const { data: orgs } = useOrganizations();
  const mutation = useBulkRegistration();
  const [file, setFile] = useState<File | null>(null);
  const [fileFormat, setFileFormat] = useState<string>("");
  const [orgId, setOrgId] = useState("");
  const [result, setResult] = useState<BulkRegistrationResponse | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const detectFormat = (name: string): string => {
    const ext = name.split(".").pop()?.toLowerCase();
    if (ext === "sdf" || ext === "sd") return "sdf";
    if (ext === "csv") return "csv";
    if (ext === "xlsx" || ext === "xls") return "xlsx";
    return "";
  };

  const handleFile = (f: File) => {
    setFile(f);
    setFileFormat(detectFormat(f.name));
    setResult(null);
  };

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  }, []);

  const handleSubmit = () => {
    if (!file || !fileFormat || !orgId) return;
    mutation.mutate(
      { file, fileFormat, originatingOrgId: orgId },
      { onSuccess: (data) => setResult(data) }
    );
  };

  const handleClose = (nextOpen: boolean) => {
    if (!nextOpen) {
      setFile(null);
      setFileFormat("");
      setOrgId("");
      setResult(null);
    }
    onOpenChange(nextOpen);
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Bulk Registration</DialogTitle>
          <DialogDescription>
            Upload an SDF, CSV, or XLSX file to register molecules in bulk.
          </DialogDescription>
          <Button
            variant="link"
            size="sm"
            className="mt-1 h-auto p-0 text-xs"
            onClick={downloadCsvTemplate}
          >
            <Download className="mr-1 h-3 w-3" />
            Download CSV template
          </Button>
        </DialogHeader>

        {!result ? (
          <>
            <div className="space-y-4 py-4">
              {/* Drop zone */}
              <div
                className={`flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 text-center transition-colors ${
                  dragOver
                    ? "border-primary bg-primary/5"
                    : "border-muted-foreground/25"
                }`}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
              >
                <FileUp className="mb-3 h-10 w-10 text-muted-foreground/40" />
                {file ? (
                  <p className="text-sm font-medium">{file.name}</p>
                ) : (
                  <>
                    <p className="text-sm font-medium">
                      Drop file here or click to browse
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Supports .sdf, .csv, .xlsx
                    </p>
                  </>
                )}
                <input
                  type="file"
                  accept=".sdf,.sd,.csv,.xlsx,.xls"
                  className="absolute inset-0 cursor-pointer opacity-0"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) handleFile(f);
                  }}
                  style={{ position: "relative", marginTop: 8 }}
                />
              </div>

              <div className="grid gap-2">
                <Label>File Format</Label>
                <Select value={fileFormat} onValueChange={setFileFormat}>
                  <SelectTrigger>
                    <SelectValue placeholder="Auto-detected from extension" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="sdf">SDF (Structure Data File)</SelectItem>
                    <SelectItem value="csv">CSV (Comma Separated)</SelectItem>
                    <SelectItem value="xlsx">XLSX (Excel)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="grid gap-2">
                <Label>Originating Organization</Label>
                <Select value={orgId} onValueChange={setOrgId}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select organization..." />
                  </SelectTrigger>
                  <SelectContent>
                    {orgs?.map(
                      (org: { id: string; name: string }) => (
                        <SelectItem key={org.id} value={org.id}>
                          {org.name}
                        </SelectItem>
                      )
                    )}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <DialogFooter>
              <Button
                onClick={handleSubmit}
                disabled={!file || !fileFormat || !orgId || mutation.isPending}
              >
                <Upload className="mr-2 h-4 w-4" />
                {mutation.isPending ? "Uploading..." : "Upload & Register"}
              </Button>
            </DialogFooter>
          </>
        ) : (
          <div className="space-y-4 py-4">
            {/* Results summary */}
            <div className="flex items-center gap-4">
              {result.error_count === 0 ? (
                <CheckCircle2 className="h-8 w-8 text-green-500" />
              ) : (
                <AlertCircle className="h-8 w-8 text-yellow-500" />
              )}
              <div>
                <p className="font-semibold">
                  {result.status === "completed"
                    ? "Registration Complete"
                    : "Completed with Errors"}
                </p>
                <div className="mt-1 flex gap-3 text-sm">
                  <Badge variant="default">
                    {result.registered_count} registered
                  </Badge>
                  <Badge variant="secondary">
                    {result.duplicate_count} duplicates
                  </Badge>
                  {result.error_count > 0 && (
                    <Badge variant="destructive">
                      {result.error_count} errors
                    </Badge>
                  )}
                </div>
              </div>
            </div>

            {/* Per-item results */}
            <div className="max-h-60 overflow-auto rounded border">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-background">
                  <tr className="border-b">
                    <th className="px-3 py-2 text-left">Row</th>
                    <th className="px-3 py-2 text-left">Status</th>
                    <th className="px-3 py-2 text-left">Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {result.items.map((item) => (
                    <tr key={item.row_index} className="border-b last:border-0">
                      <td className="px-3 py-1.5 font-mono">
                        {item.row_index + 1}
                      </td>
                      <td className="px-3 py-1.5">
                        {item.success ? (
                          <CheckCircle2 className="h-4 w-4 text-green-500" />
                        ) : (
                          <XCircle className="h-4 w-4 text-red-500" />
                        )}
                      </td>
                      <td className="px-3 py-1.5 text-muted-foreground">
                        {item.error ??
                          (item.is_new ? "New molecule" : "Duplicate")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <DialogFooter>
              <Button onClick={() => handleClose(false)}>Done</Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
