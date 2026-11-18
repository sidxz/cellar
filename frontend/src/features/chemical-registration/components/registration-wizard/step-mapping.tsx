"use client";

import { Button } from "@/shared/components/ui/button";
import { Card, CardContent } from "@/shared/components/ui/card";
import { Input } from "@/shared/components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import type { ColumnMappingBody, ColumnTarget } from "@/shared/lib/api/model";
import { AlertTriangle, ArrowLeft, Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useRegistrationWizard } from "../../hooks/use-registration-wizard";
import { useSuggestColumnMapping } from "../../hooks/use-registration-wizard-api";
import {
  TARGET_GROUPS,
  TARGET_LABELS,
  isLabelled,
  isMulti,
  mappingProblem,
} from "../../lib/column-targets";
import { readFileColumns } from "../../lib/read-file-columns";

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
  const [readError, setReadError] = useState<string | null>(null);
  const suggestedFor = useRef<object | null>(null);
  const isSdf = bulkInput.fileFormat === "sdf";

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

  // Start from where each header goes by its name, once per set of columns.
  // biome-ignore lint/correctness/useExhaustiveDependencies: suggest once per columns object; the mutation and setter are stable.
  useEffect(() => {
    if (!bulkColumns || bulkMapping || suggestedFor.current === bulkColumns) return;
    suggestedFor.current = bulkColumns;
    suggest
      .mutateAsync(bulkColumns.headers)
      .then((m) => setBulkMapping(m))
      .catch(() => {
        // Toast comes from the hook; fall back to "Don't import" everywhere.
        setBulkMapping({
          columns: bulkColumns.headers.map((header) => ({ header, target: "ignore" })),
        });
      });
  }, [bulkColumns, bulkMapping]);

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
  // Single-valued targets already used, and by which column.
  const takenBy = new Map<ColumnTarget, string>();
  for (const c of mapping.columns) if (!isMulti(c.target)) takenBy.set(c.target, c.header);

  const updateColumn = (header: string, patch: Partial<ColumnMappingBody["columns"][number]>) =>
    setBulkMapping({
      columns: mapping.columns.map((c) => (c.header === header ? { ...c, ...patch } : c)),
    });

  const onTarget = (header: string, current: string | null | undefined, target: ColumnTarget) =>
    updateColumn(header, {
      target,
      source: isLabelled(target) ? current?.trim() || header : null,
    });

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold">Match columns</h2>
        <p className="text-sm text-muted-foreground">
          Each column in your file goes to one place in ChemCellar. Several columns can go to the
          same place.
        </p>
      </div>

      <Card>
        <CardContent className="px-0 py-0">
          <div className="max-h-[520px] overflow-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-muted/80 backdrop-blur">
                <tr className="border-b text-xs">
                  <th className="px-3 py-2 text-left font-medium">Column in file</th>
                  <th className="px-3 py-2 text-left font-medium">Sample values</th>
                  <th className="px-3 py-2 text-left font-medium">Goes to</th>
                  <th className="px-3 py-2 text-left font-medium">Source</th>
                </tr>
              </thead>
              <tbody>
                {mapping.columns.map((c) => {
                  const samples = bulkColumns.samples[c.header] ?? [];
                  return (
                    <tr key={c.header} className="border-b last:border-b-0">
                      <td className="px-3 py-2 font-medium">{c.header}</td>
                      <td className="px-3 py-2 text-xs text-muted-foreground max-w-[280px] truncate">
                        {samples.length > 0 ? samples.join(", ") : "(empty in this file)"}
                      </td>
                      <td className="px-3 py-2">
                        <Select
                          value={c.target}
                          onValueChange={(v) => onTarget(c.header, c.source, v as ColumnTarget)}
                        >
                          <SelectTrigger className="h-8 w-56" aria-label={`Where ${c.header} goes`}>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {TARGET_GROUPS.map((g) => (
                              <SelectGroup key={g.label}>
                                <SelectLabel>{g.label}</SelectLabel>
                                {g.targets
                                  // SDF: the structure always comes from the record itself.
                                  .filter((t) => !(isSdf && t === "smiles"))
                                  .map((t) => {
                                    const owner = takenBy.get(t);
                                    const usedElsewhere = !!owner && owner !== c.header;
                                    return (
                                      <SelectItem key={t} value={t} disabled={usedElsewhere}>
                                        {TARGET_LABELS[t]}
                                        {usedElsewhere ? ` (used by ${owner})` : ""}
                                      </SelectItem>
                                    );
                                  })}
                              </SelectGroup>
                            ))}
                            <SelectSeparator />
                            <SelectItem value="ignore">{TARGET_LABELS.ignore}</SelectItem>
                          </SelectContent>
                        </Select>
                      </td>
                      <td className="px-3 py-2">
                        {isLabelled(c.target) && (
                          <Input
                            className="h-8 w-56"
                            value={c.source ?? ""}
                            onChange={(e) => updateColumn(c.header, { source: e.target.value })}
                            aria-label={`Source for ${c.header}`}
                          />
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <div className="flex items-center justify-between border-t pt-4">
        <Button variant="outline" onClick={prevStep}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back
        </Button>
        <div className="flex items-center gap-3">
          {problem && <p className="text-sm text-muted-foreground">{problem}</p>}
          <Button onClick={nextStep} disabled={!!problem}>
            Preview
          </Button>
        </div>
      </div>
    </div>
  );
}
