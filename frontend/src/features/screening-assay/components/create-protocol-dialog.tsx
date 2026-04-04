"use client";

import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import {
  Card,
  CardContent,
} from "@/shared/components/ui/card";
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
import { Separator } from "@/shared/components/ui/separator";
import { Textarea } from "@/shared/components/ui/textarea";
import { useCreateProtocol } from "../hooks/use-protocols";
import { useTargets } from "../hooks/use-targets";
import {
  PROTOCOL_TYPE_LABELS,
  READOUT_AGGREGATION_LABELS,
  READOUT_DATA_TYPE_LABELS,
  READOUT_NORMALIZATION_LABELS,
  type CreateReadoutDefinitionInput,
  type ProtocolType,
} from "../types";

interface CreateProtocolDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface ReadoutDefState {
  name: string;
  data_type: string;
  unit: string;
  aggregation: string;
  normalization: string;
  display_order: number;
}

function emptyReadoutDef(order: number): ReadoutDefState {
  return {
    name: "",
    data_type: "numeric",
    unit: "",
    aggregation: "none",
    normalization: "none",
    display_order: order,
  };
}

export function CreateProtocolDialog({
  open,
  onOpenChange,
}: CreateProtocolDialogProps) {
  const createMutation = useCreateProtocol();
  const { data: targets } = useTargets();

  const [name, setName] = useState("");
  const [protocolType, setProtocolType] = useState<string>("biochemical");
  const [targetId, setTargetId] = useState<string>("");
  const [category, setCategory] = useState("");
  const [description, setDescription] = useState("");
  const [readoutDefs, setReadoutDefs] = useState<ReadoutDefState[]>([
    emptyReadoutDef(1),
  ]);

  const resetForm = () => {
    setName("");
    setProtocolType("biochemical");
    setTargetId("");
    setCategory("");
    setDescription("");
    setReadoutDefs([emptyReadoutDef(1)]);
  };

  const addReadout = () => {
    setReadoutDefs((prev) => [...prev, emptyReadoutDef(prev.length + 1)]);
  };

  const removeReadout = (index: number) => {
    setReadoutDefs((prev) => prev.filter((_, i) => i !== index));
  };

  const updateReadout = (
    index: number,
    field: keyof ReadoutDefState,
    value: string | number
  ) => {
    setReadoutDefs((prev) =>
      prev.map((rd, i) => (i === index ? { ...rd, [field]: value } : rd))
    );
  };

  const validReadouts = readoutDefs.filter((rd) => rd.name.trim());
  const canSubmit =
    name.trim() && validReadouts.length > 0 && !createMutation.isPending;

  const handleSubmit = () => {
    const readout_definitions: CreateReadoutDefinitionInput[] =
      validReadouts.map((rd) => ({
        name: rd.name.trim(),
        data_type: rd.data_type as CreateReadoutDefinitionInput["data_type"],
        unit: rd.unit || null,
        aggregation:
          rd.aggregation as CreateReadoutDefinitionInput["aggregation"],
        normalization:
          rd.normalization as CreateReadoutDefinitionInput["normalization"],
        display_order: rd.display_order,
      }));

    createMutation.mutate(
      {
        name: name.trim(),
        protocol_type: protocolType as ProtocolType,
        target_id: targetId || null,
        category: category || null,
        description: description || null,
        readout_definitions,
      },
      {
        onSuccess: () => {
          onOpenChange(false);
          resetForm();
        },
      }
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>New Protocol</DialogTitle>
          <DialogDescription>
            Define a screening protocol with readout definitions.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          {/* Basic info */}
          <div className="grid gap-2">
            <Label>Name</Label>
            <Input
              placeholder="e.g., EGFR Kinase IC50"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Type</Label>
              <Select value={protocolType} onValueChange={setProtocolType}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(PROTOCOL_TYPE_LABELS).map(
                    ([value, label]) => (
                      <SelectItem key={value} value={value}>
                        {label}
                      </SelectItem>
                    )
                  )}
                </SelectContent>
              </Select>
            </div>

            <div className="grid gap-2">
              <Label>Target (optional)</Label>
              <Select value={targetId} onValueChange={setTargetId}>
                <SelectTrigger>
                  <SelectValue placeholder="Select target..." />
                </SelectTrigger>
                <SelectContent>
                  {targets?.map((t) => (
                    <SelectItem key={t.id} value={t.id}>
                      {t.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid gap-2">
            <Label>Category (optional)</Label>
            <Input
              placeholder="e.g., Primary Screen, Counter Screen"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <Label>Description</Label>
            <Textarea
              placeholder="Optional description..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          <Separator />

          {/* Readout Definitions */}
          <div className="flex items-center justify-between">
            <Label className="text-base font-semibold">
              Readout Definitions
            </Label>
            <Button type="button" variant="outline" size="sm" onClick={addReadout}>
              <Plus className="mr-2 h-4 w-4" />
              Add Readout
            </Button>
          </div>

          <div className="space-y-3">
            {readoutDefs.map((rd, index) => (
              <Card key={index}>
                <CardContent className="pt-4">
                  <div className="flex items-start justify-between gap-2">
                    <div className="grid flex-1 gap-3">
                      <div className="grid grid-cols-2 gap-3">
                        <div className="grid gap-1">
                          <Label className="text-xs">Name</Label>
                          <Input
                            placeholder="e.g., % Inhibition"
                            value={rd.name}
                            onChange={(e) =>
                              updateReadout(index, "name", e.target.value)
                            }
                          />
                        </div>
                        <div className="grid gap-1">
                          <Label className="text-xs">Data Type</Label>
                          <Select
                            value={rd.data_type}
                            onValueChange={(v) =>
                              updateReadout(index, "data_type", v)
                            }
                          >
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {Object.entries(READOUT_DATA_TYPE_LABELS).map(
                                ([value, label]) => (
                                  <SelectItem key={value} value={value}>
                                    {label}
                                  </SelectItem>
                                )
                              )}
                            </SelectContent>
                          </Select>
                        </div>
                      </div>

                      <div className="grid grid-cols-3 gap-3">
                        <div className="grid gap-1">
                          <Label className="text-xs">Unit</Label>
                          <Input
                            placeholder="e.g., nM"
                            value={rd.unit}
                            onChange={(e) =>
                              updateReadout(index, "unit", e.target.value)
                            }
                          />
                        </div>
                        <div className="grid gap-1">
                          <Label className="text-xs">Aggregation</Label>
                          <Select
                            value={rd.aggregation}
                            onValueChange={(v) =>
                              updateReadout(index, "aggregation", v)
                            }
                          >
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {Object.entries(READOUT_AGGREGATION_LABELS).map(
                                ([value, label]) => (
                                  <SelectItem key={value} value={value}>
                                    {label}
                                  </SelectItem>
                                )
                              )}
                            </SelectContent>
                          </Select>
                        </div>
                        <div className="grid gap-1">
                          <Label className="text-xs">Normalization</Label>
                          <Select
                            value={rd.normalization}
                            onValueChange={(v) =>
                              updateReadout(index, "normalization", v)
                            }
                          >
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {Object.entries(
                                READOUT_NORMALIZATION_LABELS
                              ).map(([value, label]) => (
                                <SelectItem key={value} value={value}>
                                  {label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                      </div>
                    </div>

                    {readoutDefs.length > 1 && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="mt-5 shrink-0"
                        onClick={() => removeReadout(index)}
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>

        <DialogFooter>
          <Button onClick={handleSubmit} disabled={!canSubmit}>
            {createMutation.isPending ? "Creating..." : "Create Protocol"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
