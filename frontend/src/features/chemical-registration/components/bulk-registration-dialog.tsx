"use client";

import { useCallback, useState } from "react";
import {
  Download,
  FileUp,
  Upload,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Loader2,
} from "lucide-react";
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
  useBulkRegistrationStatus,
  type BulkRegistrationResponse,
  type BulkRegistrationResult,
} from "../hooks/use-bulk-registration";

function downloadCsvTemplate() {
  const header =
    "name,smiles,molecule_type,cas_number,vendor_id,chembl_id,pubchem_cid,custom_id,amount,amount_unit,salt_code,salt_stoichiometry,purity,source,appearance";
  const example1 =
    "Aspirin,CC(=O)Oc1ccccc1C(O)=O,small_molecule,50-78-2,VENDOR-001,CHEMBL25,2244,,,mg,,,99.5,synthesized,white powder";
  const example2 =
    "Sodium Aspirin,[Na+].CC(=O)Oc1ccccc1C(=O)[O-],small_molecule,,,,,,100,mg,Na,1,98.0,purchased,";
  const example3 =
    "Caffeine,Cn1c(=O)c2c(ncn2C)n(C)c1=O,small_molecule,58-08-2,,CHEMBL113,2519,,50,mg,,,99.9,synthesized,white crystals";
  const csv = [header, example1, example2, example3].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "bulk_registration_template.csv";
  a.click();
  URL.revokeObjectURL(url);
}

type Phase = "upload" | "progress" | "sync-result" | "async-done";

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
  const [phase, setPhase] = useState<Phase>("upload");
  const [syncResult, setSyncResult] = useState<BulkRegistrationResponse | null>(
    null
  );
  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const { data: asyncStatus } = useBulkRegistrationStatus(
    phase === "progress" ? workflowId : null
  );

  // Transition to done when async workflow completes
  if (
    phase === "progress" &&
    asyncStatus &&
    (asyncStatus.status === "completed" ||
      asyncStatus.status === "completed_with_errors")
  ) {
    setPhase("async-done");
  }

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
      {
        onSuccess: (result: BulkRegistrationResult) => {
          if (result.mode === "sync") {
            setSyncResult(result.data);
            setPhase("sync-result");
          } else {
            setWorkflowId(result.workflowId);
            setPhase("progress");
          }
        },
      }
    );
  };

  const handleClose = (nextOpen: boolean) => {
    if (!nextOpen) {
      setFile(null);
      setFileFormat("");
      setOrgId("");
      setPhase("upload");
      setSyncResult(null);
      setWorkflowId(null);
    }
    onOpenChange(nextOpen);
  };

  const processedCount = asyncStatus
    ? asyncStatus.registered_count +
      asyncStatus.duplicate_count +
      asyncStatus.error_count
    : 0;
  const percent =
    asyncStatus && asyncStatus.total_count > 0
      ? Math.round((processedCount / asyncStatus.total_count) * 100)
      : 0;

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Bulk Registration</DialogTitle>
          <DialogDescription>
            Upload an SDF, CSV, or XLSX file to register molecules in bulk.
          </DialogDescription>
          {phase === "upload" && (
            <Button
              variant="link"
              size="sm"
              className="mt-1 h-auto p-0 text-xs"
              onClick={downloadCsvTemplate}
            >
              <Download className="mr-1 h-3 w-3" />
              Download CSV template
            </Button>
          )}
        </DialogHeader>

        {/* Phase: Upload */}
        {phase === "upload" && (
          <>
            <div className="space-y-4 py-4">
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
                    {orgs?.map((org: { id: string; name: string }) => (
                      <SelectItem key={org.id} value={org.id}>
                        {org.name}
                      </SelectItem>
                    ))}
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
        )}

        {/* Phase: Async Progress */}
        {phase === "progress" && (
          <div className="space-y-4 py-4">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              {asyncStatus
                ? `Processing... (chunk ${asyncStatus.chunks_processed} of ${asyncStatus.chunks_total})`
                : "Starting import..."}
            </div>

            {asyncStatus && asyncStatus.total_count > 0 && (
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>
                    {processedCount.toLocaleString()} of{" "}
                    {asyncStatus.total_count.toLocaleString()}
                  </span>
                  <span>{percent}%</span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-primary transition-all duration-300"
                    style={{ width: `${percent}%` }}
                  />
                </div>
              </div>
            )}

            {asyncStatus && (
              <div className="grid grid-cols-3 gap-3">
                <CounterCard
                  label="Registered"
                  value={asyncStatus.registered_count}
                  color="text-green-600"
                />
                <CounterCard
                  label="Duplicate"
                  value={asyncStatus.duplicate_count}
                  color="text-blue-600"
                />
                <CounterCard
                  label="Errors"
                  value={asyncStatus.error_count}
                  color="text-destructive"
                />
              </div>
            )}

            <DialogFooter>
              <Button variant="outline" onClick={() => handleClose(false)}>
                Close (continues in background)
              </Button>
            </DialogFooter>
          </div>
        )}

        {/* Phase: Async Done */}
        {phase === "async-done" && asyncStatus && (
          <div className="space-y-4 py-4">
            <div className="flex items-center gap-4">
              {asyncStatus.error_count === 0 ? (
                <CheckCircle2 className="h-8 w-8 text-green-500" />
              ) : (
                <AlertCircle className="h-8 w-8 text-yellow-500" />
              )}
              <div>
                <p className="font-semibold">
                  {asyncStatus.status === "completed"
                    ? "Registration Complete"
                    : "Completed with Errors"}
                </p>
                <div className="mt-1 flex gap-3 text-sm">
                  <Badge variant="default">
                    {asyncStatus.registered_count} registered
                  </Badge>
                  <Badge variant="secondary">
                    {asyncStatus.duplicate_count} duplicates
                  </Badge>
                  {asyncStatus.error_count > 0 && (
                    <Badge variant="destructive">
                      {asyncStatus.error_count} errors
                    </Badge>
                  )}
                </div>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              {asyncStatus.total_count.toLocaleString()} total molecules
              processed
            </p>
            <DialogFooter>
              <Button onClick={() => handleClose(false)}>Done</Button>
            </DialogFooter>
          </div>
        )}

        {/* Phase: Sync Result (fallback) */}
        {phase === "sync-result" && syncResult && (
          <div className="space-y-4 py-4">
            <div className="flex items-center gap-4">
              {syncResult.error_count === 0 ? (
                <CheckCircle2 className="h-8 w-8 text-green-500" />
              ) : (
                <AlertCircle className="h-8 w-8 text-yellow-500" />
              )}
              <div>
                <p className="font-semibold">
                  {syncResult.status === "completed"
                    ? "Registration Complete"
                    : "Completed with Errors"}
                </p>
                <div className="mt-1 flex gap-3 text-sm">
                  <Badge variant="default">
                    {syncResult.registered_count} registered
                  </Badge>
                  <Badge variant="secondary">
                    {syncResult.duplicate_count} duplicates
                  </Badge>
                  {syncResult.error_count > 0 && (
                    <Badge variant="destructive">
                      {syncResult.error_count} errors
                    </Badge>
                  )}
                </div>
              </div>
            </div>

            <div className="max-h-60 overflow-auto rounded border">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-background">
                  <tr className="border-b">
                    <th className="px-3 py-2 text-left">Row</th>
                    <th className="px-3 py-2 text-left">Status</th>
                    <th className="px-3 py-2 text-left">Batch</th>
                    <th className="px-3 py-2 text-left">Salt</th>
                    <th className="px-3 py-2 text-left">Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {syncResult.items.map((item) => (
                    <tr key={item.row_index} className="border-b last:border-0">
                      <td className="px-3 py-1.5 font-mono">
                        {item.row_index + 1}
                      </td>
                      <td className="px-3 py-1.5">
                        {item.success ? (
                          <CheckCircle2 className="h-4 w-4 text-green-500" />
                        ) : (
                          <XCircle className="h-4 w-4 text-destructive" />
                        )}
                      </td>
                      <td className="px-3 py-1.5 font-mono text-muted-foreground">
                        {item.batch_number ?? "\u2014"}
                      </td>
                      <td className="px-3 py-1.5 text-muted-foreground">
                        {item.salt_matched ? "matched" : "\u2014"}
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

function CounterCard({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div className="rounded-md border p-2.5 text-center">
      <div className={`text-lg font-semibold tabular-nums ${color}`}>
        {value.toLocaleString()}
      </div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  );
}
