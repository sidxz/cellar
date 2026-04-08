"use client";

import { useState } from "react";
import { Check, AlertTriangle, Loader2 } from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import {
  useCddProtocols,
  useCddProtocolPreview,
  useImportCddProtocol,
} from "../hooks/use-cdd-import";

interface CddImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onImported?: (protocolId: string) => void;
}

type Step = "select" | "preview" | "importing";

export function CddImportDialog({
  open,
  onOpenChange,
  onImported,
}: CddImportDialogProps) {
  const [step, setStep] = useState<Step>("select");
  const [selectedCddId, setSelectedCddId] = useState<number | null>(null);
  const [nameOverride, setNameOverride] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: protocols, isLoading: protocolsLoading, error: protocolsError } =
    useCddProtocols(open);
  const { data: preview, isLoading: previewLoading } =
    useCddProtocolPreview(step === "preview" ? selectedCddId : null);
  const importMutation = useImportCddProtocol();

  const reset = () => {
    setStep("select");
    setSelectedCddId(null);
    setNameOverride("");
    setError(null);
  };

  const handleOpenChange = (v: boolean) => {
    if (!v) reset();
    onOpenChange(v);
  };

  const handleSelectProtocol = (cddId: number) => {
    setSelectedCddId(cddId);
    setStep("preview");
    setError(null);
  };

  const handleImport = async () => {
    if (selectedCddId === null) return;
    setStep("importing");
    setError(null);
    try {
      const result = await importMutation.mutateAsync({
        cddId: selectedCddId,
        nameOverride: nameOverride || undefined,
      });
      handleOpenChange(false);
      if (onImported && result && typeof result === "object" && "id" in result) {
        onImported((result as { id: string }).id);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Import failed");
      setStep("preview");
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Import Protocol from CDD Vault</DialogTitle>
        </DialogHeader>

        {error && (
          <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {/* Step 1: Select */}
        {step === "select" && (
          <div className="space-y-4">
            {protocolsLoading && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading protocols from CDD Vault...
              </div>
            )}
            {protocolsError && (
              <p className="text-sm text-destructive">
                {protocolsError instanceof Error
                  ? protocolsError.message
                  : "Failed to load CDD protocols"}
              </p>
            )}
            {protocols && protocols.length === 0 && (
              <p className="text-sm text-muted-foreground">
                No protocols found in CDD Vault.
              </p>
            )}
            {protocols && protocols.length > 0 && (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Protocol Name</TableHead>
                    <TableHead className="w-[100px]">Readouts</TableHead>
                    <TableHead className="w-[80px]" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {protocols.map((p) => (
                    <TableRow key={p.cdd_id}>
                      <TableCell className="font-medium">{p.name}</TableCell>
                      <TableCell>{p.readout_count}</TableCell>
                      <TableCell>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleSelectProtocol(p.cdd_id)}
                        >
                          Preview
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>
        )}

        {/* Step 2: Preview */}
        {step === "preview" && (
          <div className="space-y-4">
            {previewLoading && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading protocol details...
              </div>
            )}
            {preview && (
              <>
                <div className="grid gap-2">
                  <Label>Protocol Name</Label>
                  <Input
                    value={nameOverride || preview.name}
                    onChange={(e) => setNameOverride(e.target.value)}
                    placeholder={preview.name}
                  />
                </div>

                {preview.readouts.length > 0 && (
                  <div>
                    <h4 className="mb-2 text-sm font-semibold">
                      Mapped Readouts ({preview.readouts.length})
                    </h4>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead />
                          <TableHead>Name</TableHead>
                          <TableHead>Type</TableHead>
                          <TableHead>Unit</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {preview.readouts.map((r, i) => (
                          <TableRow key={i}>
                            <TableCell>
                              <Check className="h-4 w-4 text-green-500" />
                            </TableCell>
                            <TableCell className="font-medium">
                              {r.name}
                            </TableCell>
                            <TableCell>
                              <Badge variant="outline">{r.data_type}</Badge>
                            </TableCell>
                            <TableCell>{r.unit ?? "\u2014"}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}

                {preview.warnings.length > 0 && (
                  <div>
                    <h4 className="mb-2 text-sm font-semibold text-amber-600">
                      Skipped ({preview.warnings.length})
                    </h4>
                    {preview.warnings.map((w, i) => (
                      <div
                        key={i}
                        className="flex items-start gap-2 rounded-md bg-amber-500/10 p-2 text-sm"
                      >
                        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
                        <div>
                          <span className="font-medium">{w.field_name}</span>
                          <span className="text-muted-foreground">
                            {" "}&mdash; {w.reason}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {preview.conditions.length > 0 && (
                  <div>
                    <h4 className="mb-2 text-sm font-semibold">
                      Conditions ({preview.conditions.length})
                    </h4>
                    <div className="flex flex-wrap gap-2">
                      {preview.conditions.map((c, i) => (
                        <Badge key={i} variant="secondary">
                          {c.name} ({c.data_type})
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}

            <DialogFooter>
              <Button variant="outline" onClick={() => setStep("select")}>
                Back
              </Button>
              <Button
                onClick={handleImport}
                disabled={!preview || preview.readouts.length === 0}
              >
                Import as Draft
              </Button>
            </DialogFooter>
          </div>
        )}

        {/* Step 3: Importing */}
        {step === "importing" && (
          <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Importing protocol...
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
