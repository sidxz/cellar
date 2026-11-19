"use client";

import { Button } from "@/shared/components/ui/button";
import { Card, CardContent } from "@/shared/components/ui/card";
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
import { AlertTriangle, ArrowLeft, Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import {
  useBulkRegistrationMappings,
  useSaveBulkRegistrationMapping,
} from "../../hooks/use-bulk-registration-mappings";
import { useRegistrationWizard } from "../../hooks/use-registration-wizard";
import { useSuggestColumnMapping } from "../../hooks/use-registration-wizard-api";
import {
  SAVED_MAPPING_MIN_SCORE,
  applySavedMapping,
  mappingProblem,
  scoreSavedMapping,
} from "../../lib/column-targets";
import { readFileColumns } from "../../lib/read-file-columns";
import { ColumnMappingTable } from "../column-mapping-table";

// ---------------------------------------------------------------------------
// StepMapping — "Match columns": each column of the file goes to one place
// ---------------------------------------------------------------------------

export function StepMapping() {
  const bulkInput = useRegistrationWizard((s) => s.bulkInput);
  const bulkColumns = useRegistrationWizard((s) => s.bulkColumns);
  const setBulkColumns = useRegistrationWizard((s) => s.setBulkColumns);
  const bulkMapping = useRegistrationWizard((s) => s.bulkMapping);
  const setBulkMapping = useRegistrationWizard((s) => s.setBulkMapping);
  const nextStep = useRegistrationWizard((s) => s.nextStep);
  const prevStep = useRegistrationWizard((s) => s.prevStep);

  const suggest = useSuggestColumnMapping();
  const saved = useBulkRegistrationMappings();
  const save = useSaveBulkRegistrationMapping();
  const [readError, setReadError] = useState<string | null>(null);
  const [appliedId, setAppliedId] = useState<string | null>(null);
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveName, setSaveName] = useState("");
  const suggestedFor = useRef<object | null>(null);
  const isSdf = bulkInput.fileFormat === "sdf";
  const savedMappings = saved.data ?? [];
  const applied = savedMappings.find((m) => m.id === appliedId) ?? null;

  // Read the file's columns once per file.
  useEffect(() => {
    if (!bulkInput.file || bulkColumns) return;
    let cancelled = false;
    setReadError(null);
    readFileColumns(bulkInput.file, bulkInput.fileFormat)
      .then((cols) => {
        if (!cancelled) setBulkColumns(cols);
      })
      .catch((err: Error) => {
        if (!cancelled) setReadError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [bulkInput.file, bulkInput.fileFormat, bulkColumns, setBulkColumns]);

  // Start from where each header goes by its name, then lay the best-fitting saved
  // mapping over it — once per set of columns, after the saved list has loaded.
  // biome-ignore lint/correctness/useExhaustiveDependencies: run once per columns object; the mutation and setters are stable.
  useEffect(() => {
    if (!bulkColumns || bulkMapping || suggestedFor.current === bulkColumns) return;
    if (saved.isPending) return;
    suggestedFor.current = bulkColumns;
    suggest
      .mutateAsync(bulkColumns.headers)
      .then((m) => {
        let best: (typeof savedMappings)[number] | null = null;
        let bestScore = SAVED_MAPPING_MIN_SCORE;
        for (const sm of savedMappings) {
          const score = scoreSavedMapping(sm, bulkColumns.headers);
          if (score >= bestScore) {
            best = sm;
            bestScore = score;
          }
        }
        setAppliedId(best?.id ?? null);
        setBulkMapping(best ? applySavedMapping(best, m) : m);
      })
      .catch(() => {
        // Toast comes from the hook; fall back to "Don't import" everywhere.
        setBulkMapping({
          columns: bulkColumns.headers.map((header) => ({ header, target: "ignore" })),
        });
      });
  }, [bulkColumns, bulkMapping, saved.isPending]);

  if (readError) {
    return (
      <Card>
        <CardContent className="py-8">
          <div className="flex flex-col items-center gap-4 text-center">
            <AlertTriangle className="h-8 w-8 text-destructive" />
            <div>
              <p className="text-sm font-medium">Could not read the file's columns</p>
              <p className="mt-1 text-sm text-muted-foreground">{readError}</p>
            </div>
            <Button variant="outline" onClick={prevStep}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!bulkColumns || !bulkMapping) {
    return (
      <Card>
        <CardContent className="py-12">
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <p className="text-sm text-muted-foreground">
              Reading the columns of {bulkInput.file?.name}…
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  const mapping = bulkMapping;
  const problem = mappingProblem(mapping, isSdf);
  const onSaved = (id: string) => {
    const sm = savedMappings.find((m) => m.id === id);
    if (!sm) return;
    setAppliedId(id);
    setBulkMapping(applySavedMapping(sm, mapping));
  };

  const doSave = (asNew: boolean) => {
    const id = !asNew && applied ? applied.id : undefined;
    save
      .mutateAsync({
        id,
        body: {
          name: asNew || !applied ? saveName.trim() : applied.name,
          columns: mapping.columns,
        },
      })
      .then((m) => {
        setAppliedId(m.id);
        setSaveOpen(false);
      })
      .catch(() => {
        // Toast comes from the hook.
      });
  };

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">Match columns</h2>
          <p className="text-sm text-muted-foreground">
            Each column in your file goes to one place in ChemCellar. Several columns can go to the
            same place.
          </p>
        </div>
        {savedMappings.length > 0 && (
          <div className="flex items-center gap-2">
            <Label htmlFor="saved-mapping" className="text-sm text-muted-foreground">
              Saved mapping
            </Label>
            <Select value={appliedId ?? ""} onValueChange={onSaved}>
              <SelectTrigger id="saved-mapping" className="h-8 w-56">
                <SelectValue placeholder="None" />
              </SelectTrigger>
              <SelectContent>
                {savedMappings.map((m) => (
                  <SelectItem key={m.id} value={m.id}>
                    {m.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
      </div>

      <Card>
        <CardContent className="px-0 py-0">
          <div className="max-h-[520px] overflow-auto">
            <ColumnMappingTable
              rows={mapping.columns.map((c) => ({
                key: c.header,
                label: c.header,
                samples: bulkColumns.samples[c.header] ?? [],
              }))}
              mapping={mapping}
              onChange={setBulkMapping}
              hideSmiles={isSdf}
            />
          </div>
        </CardContent>
      </Card>

      <div className="flex items-center justify-between border-t pt-4">
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={prevStep}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back
          </Button>
          <Button
            variant="ghost"
            onClick={() => {
              setSaveName(applied ? "" : (bulkInput.file?.name.replace(/\.[^.]+$/, "") ?? ""));
              setSaveOpen(true);
            }}
            disabled={!!problem}
          >
            Save mapping…
          </Button>
        </div>
        <div className="flex items-center gap-3">
          {problem && <p className="text-sm text-muted-foreground">{problem}</p>}
          <Button onClick={nextStep} disabled={!!problem}>
            Preview
          </Button>
        </div>
      </div>
      <Dialog open={saveOpen} onOpenChange={setSaveOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Save mapping</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Files with the same columns will use it next time.
          </p>
          {applied && (
            <p className="text-sm">
              You started from <span className="font-medium">{applied.name}</span>.
            </p>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="mapping-name">{applied ? "New name" : "Name"}</Label>
            <Input
              id="mapping-name"
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              placeholder="e.g. CDD export"
            />
          </div>
          <DialogFooter>
            {applied && (
              <Button variant="outline" onClick={() => doSave(false)} disabled={save.isPending}>
                Update {applied.name}
              </Button>
            )}
            <Button onClick={() => doSave(true)} disabled={save.isPending || !saveName.trim()}>
              {applied ? "Save as new" : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
