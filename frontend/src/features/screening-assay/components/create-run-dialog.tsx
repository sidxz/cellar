"use client";

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
import { Textarea } from "@/shared/components/ui/textarea";
import { zodResolver } from "@hookform/resolvers/zod";
import { Sparkles } from "lucide-react";
import { useEffect } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { usePlateTemplates } from "../hooks/use-plate-templates";
import { useCreateRun } from "../hooks/use-runs";
import { type ConditionDefinition, PLATE_FORMAT_LABELS, type PlateFormat } from "../types";
import { TargetMultiSelect } from "./target-multi-select";

// ── Schema ────────────────────────────────────────────────────────────────────

const schema = z.object({
  runDate: z.string().min(1, "Run date is required"),
  plateFormat: z.string().min(1, "Plate format is required"),
  plateTemplateId: z.string(),
  notes: z.string(),
  conditionValues: z.record(z.string(), z.string()),
  targetIds: z.array(z.string()),
});

type FormValues = z.infer<typeof schema>;

// ── Helpers ───────────────────────────────────────────────────────────────────

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

/** Pick the suggested plate format from the protocol's configured layouts.
 *  When the protocol has multiple, prefer the one with the highest well
 *  count (HTS scientists typically use 384/1536 over 96 if both are
 *  configured — 96 layouts are usually for re-test plates). */
function suggestedFormat(layouts: Record<string, string> | null | undefined): string | null {
  if (!layouts) return null;
  const formats = Object.keys(layouts);
  if (formats.length === 0) return null;
  return formats.sort((a, b) => Number(b) - Number(a))[0];
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface CreateRunDialogProps {
  protocolId: string;
  /** Protocol's configured control layouts, keyed by plate format
   *  ("96" | "384" | ...). When present, the dialog pre-fills format +
   *  template from these defaults instead of starting blank. */
  protocolControlLayouts?: Record<string, string> | null;
  /** Protocol's declared condition definitions — one input is rendered
   *  per definition so the screener can record run-time variables
   *  (Cell Line, Incubation Time, ATP Concentration, etc.). */
  conditionDefinitions?: ConditionDefinition[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function CreateRunDialog({
  protocolId,
  protocolControlLayouts,
  conditionDefinitions,
  open,
  onOpenChange,
}: CreateRunDialogProps) {
  const createMutation = useCreateRun();
  const { data: plateTemplates } = usePlateTemplates();

  const { register, handleSubmit, control, reset, setValue, watch } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      runDate: todayISO(),
      plateFormat: "96",
      plateTemplateId: "",
      notes: "",
      conditionValues: {},
      targetIds: [],
    },
  });

  // Whenever the dialog opens, re-seed format + template from the
  // protocol's configured control layouts. The deps include `open` so
  // closing and reopening the dialog re-applies the suggestion (e.g. if
  // the protocol's layouts changed in the background).
  useEffect(() => {
    if (!open) return;
    const fmt = suggestedFormat(protocolControlLayouts) ?? "96";
    reset({
      runDate: todayISO(),
      plateFormat: fmt,
      plateTemplateId: protocolControlLayouts?.[fmt] ?? "",
      notes: "",
      conditionValues: {},
      targetIds: [],
    });
  }, [open, protocolControlLayouts, reset]);

  const plateFormat = watch("plateFormat");
  const plateTemplateId = watch("plateTemplateId");
  const conditionValues = watch("conditionValues");

  // When the user manually changes the plate format, re-suggest a
  // template from the protocol's layout for the new format. Clears
  // selection if the new format has no configured layout.
  const handleFormatChange = (newFormat: string) => {
    setValue("plateFormat", newFormat);
    setValue("plateTemplateId", protocolControlLayouts?.[newFormat] ?? "");
  };

  // Filter template dropdown to the chosen plate format — a 96-well
  // template is meaningless on a 384-well run.
  const templatesForFormat = (plateTemplates ?? []).filter((t) => t.format === plateFormat);

  const formatIsSuggested =
    !!protocolControlLayouts && protocolControlLayouts[plateFormat] !== undefined;
  const templateIsSuggested =
    !!protocolControlLayouts &&
    plateTemplateId !== "" &&
    plateTemplateId !== "__none__" &&
    protocolControlLayouts[plateFormat] === plateTemplateId;

  // Build the conditions payload: skip empty values, append unit (if
  // declared on the definition) so storage shape matches existing data
  // ("ATP Concentration": "10 uM", "Cell Line": "HeLa").
  const buildConditionsPayload = (values: FormValues): Record<string, string> | null => {
    if (!conditionDefinitions || conditionDefinitions.length === 0) return null;
    const out: Record<string, string> = {};
    for (const cd of conditionDefinitions) {
      const raw = (values.conditionValues[cd.name] ?? "").trim();
      if (!raw) continue;
      const unit = cd.unit?.trim();
      out[cd.name] = unit ? `${raw} ${unit}` : raw;
    }
    return Object.keys(out).length > 0 ? out : null;
  };

  const onSubmit = (values: FormValues) => {
    createMutation.mutate(
      {
        protocol_id: protocolId,
        run_date: values.runDate,
        plate_format: values.plateFormat as PlateFormat,
        plate_template_id:
          values.plateTemplateId && values.plateTemplateId !== "__none__"
            ? values.plateTemplateId
            : null,
        notes: values.notes || null,
        conditions: buildConditionsPayload(values),
        target_ids: values.targetIds,
      },
      {
        onSuccess: () => {
          onOpenChange(false);
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New Run</DialogTitle>
          <DialogDescription>Create a screening run for this protocol.</DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)}>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label>Run Date</Label>
              <Input type="date" {...register("runDate")} />
            </div>

            <div className="grid gap-2">
              <div className="flex items-center gap-2">
                <Label>Plate Format</Label>
                {formatIsSuggested && (
                  <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                    <Sparkles className="h-3 w-3" />
                    from protocol
                  </span>
                )}
              </div>
              <Controller
                name="plateFormat"
                control={control}
                render={({ field }) => (
                  <Select
                    value={field.value}
                    onValueChange={(v) => {
                      field.onChange(v);
                      handleFormatChange(v);
                    }}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(PLATE_FORMAT_LABELS).map(([value, label]) => {
                        const hasLayout = protocolControlLayouts?.[value] !== undefined;
                        return (
                          <SelectItem key={value} value={value}>
                            <span className="flex items-center gap-2">
                              {label}
                              {hasLayout && <Sparkles className="h-3 w-3 text-muted-foreground" />}
                            </span>
                          </SelectItem>
                        );
                      })}
                    </SelectContent>
                  </Select>
                )}
              />
            </div>

            {templatesForFormat.length > 0 && (
              <div className="grid gap-2">
                <div className="flex items-center gap-2">
                  <Label>Plate Template (optional)</Label>
                  {templateIsSuggested && (
                    <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                      <Sparkles className="h-3 w-3" />
                      from protocol
                    </span>
                  )}
                </div>
                <Controller
                  name="plateTemplateId"
                  control={control}
                  render={({ field }) => (
                    <Select value={field.value || "__none__"} onValueChange={field.onChange}>
                      <SelectTrigger>
                        <SelectValue placeholder="None" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">None</SelectItem>
                        {templatesForFormat.map((t) => (
                          <SelectItem key={t.id} value={t.id}>
                            <span className="flex items-center gap-2">
                              {t.name}
                              {protocolControlLayouts?.[plateFormat] === t.id && (
                                <Sparkles className="h-3 w-3 text-muted-foreground" />
                              )}
                            </span>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                />
              </div>
            )}

            {conditionDefinitions && conditionDefinitions.length > 0 && (
              <div className="grid gap-3 rounded-lg border bg-muted/30 p-3">
                <p className="text-xs font-medium">Conditions</p>
                <p className="text-xs text-muted-foreground -mt-2">
                  Run-time variables declared on the protocol. Leave blank if not recorded.
                </p>
                {conditionDefinitions.map((cd) => {
                  const value = conditionValues[cd.name] ?? "";
                  const labelText = cd.unit ? `${cd.name} (${cd.unit})` : cd.name;
                  return (
                    <div key={cd.id} className="grid gap-1">
                      <Label className="text-xs">{labelText}</Label>
                      {cd.data_type === "pick_list" &&
                      cd.pick_list_values &&
                      cd.pick_list_values.length > 0 ? (
                        <Select
                          value={value || "__none__"}
                          onValueChange={(v) =>
                            setValue(`conditionValues.${cd.name}`, v === "__none__" ? "" : v)
                          }
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="Select..." />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="__none__">(not recorded)</SelectItem>
                            {cd.pick_list_values.map((opt) => (
                              <SelectItem key={opt} value={opt}>
                                {opt}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      ) : (
                        <Input
                          type={cd.data_type === "numeric" ? "number" : "text"}
                          inputMode={cd.data_type === "numeric" ? "decimal" : undefined}
                          placeholder={
                            cd.data_type === "numeric"
                              ? cd.unit
                                ? `e.g. 10 (${cd.unit})`
                                : "e.g. 10"
                              : undefined
                          }
                          value={value}
                          onChange={(e) => setValue(`conditionValues.${cd.name}`, e.target.value)}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            <div className="grid gap-2">
              <Label>Targets (optional)</Label>
              <Controller
                name="targetIds"
                control={control}
                render={({ field }) => (
                  <TargetMultiSelect value={field.value} onChange={field.onChange} />
                )}
              />
            </div>

            <div className="grid gap-2">
              <Label>Notes (optional)</Label>
              <Textarea placeholder="Run notes..." {...register("notes")} />
            </div>
          </div>

          <DialogFooter>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? "Creating..." : "Create Run"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
