"use client";

import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
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
import { useCreateRun } from "../hooks/use-runs";
import { usePlateTemplates } from "../hooks/use-plate-templates";
import { PLATE_FORMAT_LABELS, type PlateFormat } from "../types";

interface CreateRunDialogProps {
  protocolId: string;
  /** Protocol's configured control layouts, keyed by plate format
   *  ("96" | "384" | ...). When present, the dialog pre-fills format +
   *  template from these defaults instead of starting blank. */
  protocolControlLayouts?: Record<string, string> | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

/** Pick the suggested plate format from the protocol's configured layouts.
 *  When the protocol has multiple, prefer the one with the highest well
 *  count (HTS scientists typically use 384/1536 over 96 if both are
 *  configured — 96 layouts are usually for re-test plates). */
function suggestedFormat(
  layouts: Record<string, string> | null | undefined,
): string | null {
  if (!layouts) return null;
  const formats = Object.keys(layouts);
  if (formats.length === 0) return null;
  return formats.sort((a, b) => Number(b) - Number(a))[0];
}

export function CreateRunDialog({
  protocolId,
  protocolControlLayouts,
  open,
  onOpenChange,
}: CreateRunDialogProps) {
  const createMutation = useCreateRun();
  const { data: plateTemplates } = usePlateTemplates();
  const [runDate, setRunDate] = useState(todayISO);
  const [plateFormat, setPlateFormat] = useState<string>("96");
  const [plateTemplateId, setPlateTemplateId] = useState<string>("");
  const [notes, setNotes] = useState("");

  // Whenever the dialog opens, re-seed format + template from the
  // protocol's configured control layouts. The deps include `open` so
  // closing and reopening the dialog re-applies the suggestion (e.g. if
  // the protocol's layouts changed in the background).
  useEffect(() => {
    if (!open) return;
    const fmt = suggestedFormat(protocolControlLayouts) ?? "96";
    setPlateFormat(fmt);
    setPlateTemplateId(protocolControlLayouts?.[fmt] ?? "");
    setRunDate(todayISO());
    setNotes("");
  }, [open, protocolControlLayouts]);

  // When the user manually changes the plate format, re-suggest a
  // template from the protocol's layout for the new format. Clears
  // selection if the new format has no configured layout.
  const handleFormatChange = (newFormat: string) => {
    setPlateFormat(newFormat);
    setPlateTemplateId(protocolControlLayouts?.[newFormat] ?? "");
  };

  // Filter template dropdown to the chosen plate format — a 96-well
  // template is meaningless on a 384-well run.
  const templatesForFormat = (plateTemplates ?? []).filter(
    (t) => t.format === plateFormat,
  );

  const formatIsSuggested =
    !!protocolControlLayouts &&
    protocolControlLayouts[plateFormat] !== undefined;
  const templateIsSuggested =
    !!protocolControlLayouts &&
    plateTemplateId !== "" &&
    plateTemplateId !== "__none__" &&
    protocolControlLayouts[plateFormat] === plateTemplateId;

  const handleSubmit = () => {
    createMutation.mutate(
      {
        protocol_id: protocolId,
        run_date: runDate,
        plate_format: plateFormat as PlateFormat,
        plate_template_id:
          plateTemplateId && plateTemplateId !== "__none__"
            ? plateTemplateId
            : null,
        notes: notes || null,
      },
      {
        onSuccess: () => {
          onOpenChange(false);
        },
      }
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New Run</DialogTitle>
          <DialogDescription>
            Create a screening run for this protocol.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Run Date</Label>
            <Input
              type="date"
              value={runDate}
              onChange={(e) => setRunDate(e.target.value)}
            />
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
            <Select value={plateFormat} onValueChange={handleFormatChange}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(PLATE_FORMAT_LABELS).map(([value, label]) => {
                  const hasLayout =
                    protocolControlLayouts?.[value] !== undefined;
                  return (
                    <SelectItem key={value} value={value}>
                      <span className="flex items-center gap-2">
                        {label}
                        {hasLayout && (
                          <Sparkles className="h-3 w-3 text-muted-foreground" />
                        )}
                      </span>
                    </SelectItem>
                  );
                })}
              </SelectContent>
            </Select>
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
              <Select
                value={plateTemplateId || "__none__"}
                onValueChange={setPlateTemplateId}
              >
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
            </div>
          )}

          <div className="grid gap-2">
            <Label>Notes (optional)</Label>
            <Textarea
              placeholder="Run notes..."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            onClick={handleSubmit}
            disabled={!runDate || createMutation.isPending}
          >
            {createMutation.isPending ? "Creating..." : "Create Run"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
