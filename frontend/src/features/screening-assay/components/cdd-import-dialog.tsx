"use client";

import { useMemo, useState } from "react";
import { Check, AlertTriangle, Loader2, Search } from "lucide-react";
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
  const [selectedExternalId, setSelectedExternalId] = useState<number | null>(null);
  const [nameOverride, setNameOverride] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  const {
    data: protocols,
    isLoading: protocolsLoading,
    error: protocolsError,
  } = useCddProtocols(open);
  const { data: preview, isLoading: previewLoading } =
    useCddProtocolPreview(step === "preview" ? selectedExternalId : null);
  const importMutation = useImportCddProtocol();

  const filteredProtocols = useMemo(() => {
    if (!protocols) return [];
    if (!searchQuery.trim()) return protocols;
    const q = searchQuery.toLowerCase();
    return protocols.filter((p) => p.name.toLowerCase().includes(q));
  }, [protocols, searchQuery]);

  const reset = () => {
    setStep("select");
    setSelectedExternalId(null);
    setNameOverride("");
    setError(null);
    setSearchQuery("");
  };

  const handleOpenChange = (v: boolean) => {
    if (!v) reset();
    onOpenChange(v);
  };

  const handleSelectProtocol = (externalId: number) => {
    setSelectedExternalId(externalId);
    setStep("preview");
    setError(null);
  };

  const handleImport = async () => {
    if (selectedExternalId === null) return;
    setStep("importing");
    setError(null);
    try {
      const result = await importMutation.mutateAsync({
        externalId: selectedExternalId,
        nameOverride: nameOverride || undefined,
      });
      handleOpenChange(false);
      if (
        onImported &&
        result &&
        typeof result === "object" &&
        "id" in result
      ) {
        onImported((result as { id: string }).id);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Import failed");
      setStep("preview");
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="flex max-h-[85vh] max-w-2xl flex-col">
        <DialogHeader>
          <DialogTitle>Import Protocol from CDD Vault</DialogTitle>
          <DialogDescription>
            {step === "select" && "Select a protocol to preview its readout mapping."}
            {step === "preview" && "Review the mapping before importing."}
            {step === "importing" && "Importing..."}
          </DialogDescription>
        </DialogHeader>

        {error && (
          <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {/* Step 1: Select */}
        {step === "select" && (
          <div className="flex min-h-0 flex-1 flex-col gap-3">
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
              <>
                <div className="relative shrink-0">
                  <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                  <Input
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search protocols..."
                    className="pl-9"
                  />
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Protocol Name</TableHead>
                        <TableHead className="w-[80px] text-right">
                          Readouts
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filteredProtocols.map((p) => (
                        <TableRow
                          key={p.external_id}
                          className="cursor-pointer hover:bg-muted/50"
                          onClick={() => handleSelectProtocol(p.external_id)}
                        >
                          <TableCell className="font-medium">
                            {p.name}
                          </TableCell>
                          <TableCell className="text-right">
                            {p.readout_count}
                          </TableCell>
                        </TableRow>
                      ))}
                      {filteredProtocols.length === 0 && (
                        <TableRow>
                          <TableCell
                            colSpan={2}
                            className="text-center text-muted-foreground"
                          >
                            No protocols match your search.
                          </TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </div>
                <p className="shrink-0 text-xs text-muted-foreground">
                  {filteredProtocols.length} of {protocols.length} protocols
                </p>
              </>
            )}
          </div>
        )}

        {/* Step 2: Preview */}
        {step === "preview" && (
          <div className="flex min-h-0 flex-1 flex-col gap-4">
            {previewLoading && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading protocol details...
              </div>
            )}
            {preview && (
              <>
                {/* Fixed header: name + description + category + summary */}
                <div className="shrink-0 space-y-3">
                  <div className="grid gap-1.5">
                    <Label>Protocol Name</Label>
                    <Input
                      value={nameOverride || preview.name}
                      onChange={(e) => setNameOverride(e.target.value)}
                      placeholder={preview.name}
                    />
                  </div>
                  {(preview.description || preview.category) && (
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
                      {preview.category && (
                        <span>
                          <span className="text-muted-foreground">Category:</span>{" "}
                          <Badge variant="secondary">{preview.category}</Badge>
                        </span>
                      )}
                      {preview.description && (
                        <span className="text-muted-foreground">
                          {preview.description}
                        </span>
                      )}
                    </div>
                  )}
                  <div className="flex items-center gap-4 text-sm text-muted-foreground">
                    <span>
                      <span className="font-medium text-green-600">
                        {preview.readouts.length}
                      </span>{" "}
                      readouts mapped
                    </span>
                    {preview.conditions.length > 0 && (
                      <span>
                        <span className="font-medium">
                          {preview.conditions.length}
                        </span>{" "}
                        conditions
                      </span>
                    )}
                    {preview.warnings.length > 0 && (
                      <span>
                        <span className="font-medium text-warning">
                          {preview.warnings.length}
                        </span>{" "}
                        skipped
                      </span>
                    )}
                  </div>
                </div>

                {/* Scrollable content */}
                <div className="min-h-0 flex-1 space-y-4 overflow-y-auto">
                  {/* Mapped readouts */}
                  {preview.readouts.length > 0 && (
                    <div className="rounded-md border">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="w-8" />
                            <TableHead>Readout</TableHead>
                            <TableHead className="w-[100px]">Type</TableHead>
                            <TableHead className="w-[80px]">Unit</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {preview.readouts.map((r, i) => (
                            <TableRow key={i}>
                              <TableCell className="pr-0">
                                <Check className="h-4 w-4 text-green-500" />
                              </TableCell>
                              <TableCell className="font-medium">
                                {r.name}
                              </TableCell>
                              <TableCell>
                                <Badge variant="outline">{r.data_type}</Badge>
                              </TableCell>
                              <TableCell className="text-muted-foreground">
                                {r.unit ?? "\u2014"}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  )}

                  {/* Conditions */}
                  {preview.conditions.length > 0 && (
                    <div>
                      <h4 className="mb-2 text-sm font-medium">Conditions</h4>
                      <div className="flex flex-wrap gap-1.5">
                        {preview.conditions.map((c, i) => (
                          <Badge key={i} variant="secondary">
                            {c.name}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Warnings */}
                  {preview.warnings.length > 0 && (
                    <div className="space-y-1.5">
                      <h4 className="text-sm font-medium text-warning">
                        Skipped
                      </h4>
                      {preview.warnings.map((w, i) => (
                        <div
                          key={i}
                          className="flex items-start gap-2 rounded-md bg-warning/10 px-3 py-2 text-sm"
                        >
                          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
                          <span>
                            <span className="font-medium">{w.field_name}</span>
                            <span className="text-muted-foreground">
                              {" "}
                              &mdash; {w.reason}
                            </span>
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </>
            )}

            <DialogFooter className="shrink-0">
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
