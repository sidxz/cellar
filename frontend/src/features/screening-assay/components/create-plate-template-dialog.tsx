"use client";

import { useEffect, useState } from "react";
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
import {
  useCreatePlateTemplate,
  useUpdatePlateTemplate,
} from "../hooks/use-plate-templates";
import { PlateMapEditor } from "./plate-map-editor";
import type { PlateFormat, PlateTemplate, WellDesignation } from "../types";
import { PLATE_FORMAT_LABELS } from "../types";

/** Plate formats supported for templates. */
const TEMPLATE_FORMATS: PlateFormat[] = ["96", "384", "1536"];

interface CreatePlateTemplateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Pass a plate template to switch to edit mode. */
  plateTemplate?: PlateTemplate;
}

export function CreatePlateTemplateDialog({
  open,
  onOpenChange,
  plateTemplate,
}: CreatePlateTemplateDialogProps) {
  const isEdit = !!plateTemplate;
  const createMutation = useCreatePlateTemplate();
  const updateMutation = useUpdatePlateTemplate(plateTemplate?.id ?? "");

  const [name, setName] = useState("");
  const [format, setFormat] = useState<PlateFormat>("96");
  const [description, setDescription] = useState("");
  const [templateMap, setTemplateMap] = useState<
    Record<string, WellDesignation>
  >({});

  // Reset form when dialog opens / plateTemplate changes
  useEffect(() => {
    if (open) {
      setName(plateTemplate?.name ?? "");
      setFormat(plateTemplate?.format ?? "96");
      setDescription(plateTemplate?.description ?? "");
      setTemplateMap(plateTemplate?.template_map ?? {});
    }
  }, [open, plateTemplate]);

  const handleFormatChange = (newFormat: string) => {
    const f = newFormat as PlateFormat;
    setFormat(f);
    // Reset template map when format changes — well positions differ
    setTemplateMap({});
  };

  const mutation = isEdit ? updateMutation : createMutation;
  const canSubmit = name.trim() && !mutation.isPending;

  const handleSubmit = () => {
    const payload = {
      name: name.trim(),
      format,
      template_map: templateMap,
      description: description.trim() || null,
    };

    mutation.mutate(payload, {
      onSuccess: () => {
        onOpenChange(false);
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(95vw,1100px)] max-w-[1100px] sm:max-w-[1100px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "Edit Plate Template" : "New Plate Template"}
          </DialogTitle>
          <DialogDescription>
            {isEdit
              ? "Update the plate template configuration."
              : "Design a plate layout template for screening runs."}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          {/* Name + Format row */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="grid gap-2 sm:col-span-2">
              <Label>Name</Label>
              <Input
                placeholder="e.g., Standard 384 DRC Layout"
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && canSubmit) handleSubmit();
                }}
              />
            </div>
            <div className="grid gap-2">
              <Label>Format</Label>
              <Select value={format} onValueChange={handleFormatChange}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TEMPLATE_FORMATS.map((f) => (
                    <SelectItem key={f} value={f}>
                      {PLATE_FORMAT_LABELS[f]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Description */}
          <div className="grid gap-2">
            <Label>Description (optional)</Label>
            <Textarea
              placeholder="Brief description of the template layout..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
            />
          </div>

          {/* Plate map editor */}
          <div className="grid gap-2">
            <Label>Plate Layout</Label>
            <PlateMapEditor
              format={format}
              value={templateMap}
              onChange={setTemplateMap}
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={mutation.isPending}
          >
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!canSubmit}>
            {mutation.isPending
              ? isEdit
                ? "Saving..."
                : "Creating..."
              : isEdit
                ? "Save Changes"
                : "Create Template"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
