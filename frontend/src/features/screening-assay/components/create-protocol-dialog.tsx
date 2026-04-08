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
import { Switch } from "@/shared/components/ui/switch";
import { Textarea } from "@/shared/components/ui/textarea";
import { useVocabularies } from "@/features/workspace-config/hooks/use-vocabularies";
import { useProtocolForms, type ProtocolForm } from "@/features/workspace-config/hooks/use-protocol-forms";
import { useOntologySlots } from "@/features/workspace-config/hooks/use-ontology-slots";
import {
  OntologySearchInput,
  type OntologyTerm,
} from "@/shared/components/ontology-search-input";
import { useCreateProtocol } from "../hooks/use-protocols";
import { useTargets } from "../hooks/use-targets";
import {
  CURVE_TYPE_LABELS,
  HILL_SLOPE_CONSTRAINT_LABELS,
  NORMALIZATION_SCOPE_LABELS,
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
  is_calculated: boolean;
  calculation_formula: string;
  display_order: number;
  pick_list_values: string;
  // Dose-response config fields (flat for form state)
  dr_curve_type: string;
  dr_x_readout: string;
  dr_y_readout: string;
  dr_hill_constraint: string;
  dr_normalization_scope: string;
  dr_activity_threshold: string;
}

interface ConditionDefState {
  name: string;
  data_type: string;
  unit: string;
}

function emptyReadoutDef(order: number): ReadoutDefState {
  return {
    name: "",
    data_type: "numeric",
    unit: "",
    aggregation: "none",
    normalization: "none",
    is_calculated: false,
    calculation_formula: "",
    display_order: order,
    pick_list_values: "",
    dr_curve_type: "ic50",
    dr_x_readout: "",
    dr_y_readout: "",
    dr_hill_constraint: "unconstrained",
    dr_normalization_scope: "per_plate",
    dr_activity_threshold: "",
  };
}

function emptyConditionDef(): ConditionDefState {
  return { name: "", data_type: "text", unit: "" };
}

export function CreateProtocolDialog({
  open,
  onOpenChange,
}: CreateProtocolDialogProps) {
  const createMutation = useCreateProtocol();
  const { data: targets } = useTargets();
  const { data: vocabularies } = useVocabularies();
  const { data: protocolForms } = useProtocolForms();
  const { data: ontologySlots } = useOntologySlots();
  const categoryTerms =
    vocabularies?.find((v) => v.name === "Protocol Categories")?.terms ?? [];

  const [selectedFormId, setSelectedFormId] = useState<string>("");
  const [name, setName] = useState("");
  const [protocolType, setProtocolType] = useState<string>("biochemical");
  const [targetId, setTargetId] = useState<string>("");
  const [category, setCategory] = useState("");
  const [description, setDescription] = useState("");
  const [readoutDefs, setReadoutDefs] = useState<ReadoutDefState[]>([
    emptyReadoutDef(1),
  ]);
  const [conditionDefs, setConditionDefs] = useState<ConditionDefState[]>([]);
  const [ontologyAnnotations, setOntologyAnnotations] = useState<
    Record<string, OntologyTerm[]>
  >({});

  const resetForm = () => {
    setSelectedFormId("");
    setName("");
    setProtocolType("biochemical");
    setTargetId("");
    setCategory("");
    setDescription("");
    setReadoutDefs([emptyReadoutDef(1)]);
    setConditionDefs([]);
    setOntologyAnnotations({});
  };

  const applyForm = (form: ProtocolForm) => {
    if (form.protocol_type) {
      setProtocolType(form.protocol_type);
    }
    // Apply readout templates
    if (form.readout_templates.length > 0) {
      setReadoutDefs(
        form.readout_templates.map((tpl, i) => ({
          ...emptyReadoutDef(i + 1),
          name: (tpl.name as string) ?? "",
          data_type: (tpl.data_type as string) ?? "numeric",
          unit: (tpl.unit as string) ?? "",
          aggregation: (tpl.aggregation as string) ?? "none",
          normalization: (tpl.normalization as string) ?? "none",
        })),
      );
    }
    // Apply condition templates
    if (form.condition_templates && form.condition_templates.length > 0) {
      setConditionDefs(
        form.condition_templates.map((tpl) => ({
          name: (tpl.name as string) ?? "",
          data_type: (tpl.data_type as string) ?? "text",
          unit: (tpl.unit as string) ?? "",
        })),
      );
    }
    // Apply ontology defaults
    if (form.ontology_defaults && form.ontology_defaults.length > 0) {
      const annotations: Record<string, OntologyTerm[]> = {};
      for (const od of form.ontology_defaults) {
        const slotName = od.slot_name as string;
        const terms = od.terms as Array<Record<string, unknown>>;
        if (slotName && Array.isArray(terms)) {
          annotations[slotName] = terms.map((t) => ({
            term_id: (t.term_id as string) ?? "",
            label: (t.label as string) ?? "",
            ontology_source: (t.ontology_source as string) ?? "",
            uri: (t.uri as string) ?? null,
          }));
        }
      }
      setOntologyAnnotations(annotations);
    }
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
    value: string | number | boolean
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
      validReadouts.map((rd) => {
        const base: CreateReadoutDefinitionInput = {
          name: rd.name.trim(),
          data_type: rd.data_type as CreateReadoutDefinitionInput["data_type"],
          unit: rd.unit || null,
          aggregation:
            rd.aggregation as CreateReadoutDefinitionInput["aggregation"],
          normalization:
            rd.normalization as CreateReadoutDefinitionInput["normalization"],
          is_calculated: rd.is_calculated,
          calculation_formula: rd.is_calculated
            ? rd.calculation_formula || null
            : null,
          display_order: rd.display_order,
        };
        if (rd.data_type === "pick_list" && rd.pick_list_values.trim()) {
          base.pick_list_values = rd.pick_list_values.split(",").map((v) => v.trim()).filter(Boolean);
        }
        if (rd.data_type === "dose_response" && rd.dr_x_readout && rd.dr_y_readout) {
          base.dose_response_config = {
            curve_type: rd.dr_curve_type,
            x_readout_name: rd.dr_x_readout,
            y_readout_name: rd.dr_y_readout,
            hill_slope_constraint: rd.dr_hill_constraint,
            activity_threshold: rd.dr_activity_threshold ? parseFloat(rd.dr_activity_threshold) : null,
            normalization_scope: rd.dr_normalization_scope,
            top_constraint: null,
            bottom_constraint: null,
          } as CreateReadoutDefinitionInput["dose_response_config"];
        }
        return base;
      });

    const condition_definitions = conditionDefs
      .filter((cd) => cd.name.trim())
      .map((cd) => ({
        name: cd.name.trim(),
        data_type: cd.data_type,
        unit: cd.unit || null,
      }));

    createMutation.mutate(
      {
        name: name.trim(),
        protocol_type: protocolType as ProtocolType,
        target_id: targetId || null,
        category: category || null,
        description: description || null,
        readout_definitions,
        condition_definitions: condition_definitions.length > 0 ? condition_definitions : undefined,
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

          {/* Protocol Form Selector */}
          {protocolForms && protocolForms.length > 0 && (
            <div className="grid gap-2">
              <Label>Form Template</Label>
              <Select
                value={selectedFormId}
                onValueChange={(v) => {
                  setSelectedFormId(v);
                  if (v === "__blank__") {
                    resetForm();
                    return;
                  }
                  const form = protocolForms.find((f) => f.id === v);
                  if (form) applyForm(form);
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Blank Protocol" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__blank__">Blank Protocol</SelectItem>
                  {protocolForms.map((f) => (
                    <SelectItem key={f.id} value={f.id}>
                      {f.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Pre-fill readouts, conditions, and type from a saved form.
              </p>
            </div>
          )}

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
            {categoryTerms.length > 0 ? (
              <Select value={category} onValueChange={setCategory}>
                <SelectTrigger>
                  <SelectValue placeholder="Select category..." />
                </SelectTrigger>
                <SelectContent>
                  {categoryTerms.map((term) => (
                    <SelectItem key={term} value={term}>
                      {term}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <Input
                placeholder="e.g., Primary Screen, Counter Screen"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
              />
            )}
          </div>

          <div className="grid gap-2">
            <Label>Description</Label>
            <Textarea
              placeholder="Optional description..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          {/* Ontology Annotations */}
          {ontologySlots && ontologySlots.length > 0 && (
            <>
              <Separator />
              <Label className="text-base font-semibold">
                Ontology Annotations{" "}
                <span className="text-xs font-normal text-muted-foreground">
                  (optional)
                </span>
              </Label>
              <div className="space-y-3">
                {ontologySlots.map((slot) => (
                  <div key={slot.id} className="grid gap-1.5">
                    <Label className="text-xs">
                      {slot.label}
                      {slot.is_required && (
                        <span className="ml-1 text-destructive">*</span>
                      )}
                    </Label>
                    <OntologySearchInput
                      ontologySources={slot.ontology_sources}
                      value={ontologyAnnotations[slot.name] ?? []}
                      onChange={(terms) =>
                        setOntologyAnnotations((prev) => ({
                          ...prev,
                          [slot.name]: terms,
                        }))
                      }
                      allowFreeText={slot.allow_free_text}
                      placeholder={`Search ${slot.ontology_sources.join(", ")}...`}
                    />
                  </div>
                ))}
              </div>
            </>
          )}

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

                      {/* Calculated readout toggle */}
                      <div className="flex items-center gap-3">
                        <Switch
                          checked={rd.is_calculated}
                          onCheckedChange={(checked) =>
                            updateReadout(index, "is_calculated", checked)
                          }
                          size="sm"
                        />
                        <Label className="text-xs">Calculated</Label>
                      </div>
                      {rd.is_calculated && (
                        <div className="grid gap-1">
                          <Label className="text-xs">Formula</Label>
                          <Input
                            className="font-mono text-xs"
                            placeholder='e.g., 100 * (1 - Raw / Control)'
                            value={rd.calculation_formula}
                            onChange={(e) =>
                              updateReadout(
                                index,
                                "calculation_formula",
                                e.target.value
                              )
                            }
                          />
                          <p className="text-[11px] text-muted-foreground">
                            Use readout names as variables. Cross-protocol: @ProtocolName.ReadoutName
                          </p>
                        </div>
                      )}

                      {/* Pick List Values */}
                      {rd.data_type === "pick_list" && (
                        <div className="grid gap-1">
                          <Label className="text-xs">Pick List Values</Label>
                          <Input
                            placeholder="Comma-separated values, e.g., Active, Inactive, Inconclusive"
                            value={rd.pick_list_values}
                            onChange={(e) =>
                              updateReadout(index, "pick_list_values", e.target.value)
                            }
                          />
                        </div>
                      )}

                      {/* Dose-Response Config */}
                      {rd.data_type === "dose_response" && (
                        <div className="space-y-3 rounded-lg border bg-muted/30 p-3">
                          <p className="text-xs font-medium">Dose-Response Configuration</p>
                          <div className="grid grid-cols-3 gap-3">
                            <div className="grid gap-1">
                              <Label className="text-xs">Curve Type</Label>
                              <Select
                                value={rd.dr_curve_type}
                                onValueChange={(v) => updateReadout(index, "dr_curve_type", v)}
                              >
                                <SelectTrigger><SelectValue /></SelectTrigger>
                                <SelectContent>
                                  {Object.entries(CURVE_TYPE_LABELS).map(([v, l]) => (
                                    <SelectItem key={v} value={v}>{l}</SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="grid gap-1">
                              <Label className="text-xs">X-Axis Readout</Label>
                              <Select
                                value={rd.dr_x_readout}
                                onValueChange={(v) => updateReadout(index, "dr_x_readout", v)}
                              >
                                <SelectTrigger><SelectValue placeholder="Select..." /></SelectTrigger>
                                <SelectContent>
                                  {readoutDefs
                                    .filter((other, i) => i !== index && other.name.trim() && other.data_type === "numeric")
                                    .map((other) => (
                                      <SelectItem key={other.name} value={other.name.trim()}>
                                        {other.name}
                                      </SelectItem>
                                    ))}
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="grid gap-1">
                              <Label className="text-xs">Y-Axis Readout</Label>
                              <Select
                                value={rd.dr_y_readout}
                                onValueChange={(v) => updateReadout(index, "dr_y_readout", v)}
                              >
                                <SelectTrigger><SelectValue placeholder="Select..." /></SelectTrigger>
                                <SelectContent>
                                  {readoutDefs
                                    .filter((other, i) => i !== index && other.name.trim() && other.data_type === "numeric")
                                    .map((other) => (
                                      <SelectItem key={other.name} value={other.name.trim()}>
                                        {other.name}
                                      </SelectItem>
                                    ))}
                                </SelectContent>
                              </Select>
                            </div>
                          </div>
                          <div className="grid grid-cols-3 gap-3">
                            <div className="grid gap-1">
                              <Label className="text-xs">Hill Slope</Label>
                              <Select
                                value={rd.dr_hill_constraint}
                                onValueChange={(v) => updateReadout(index, "dr_hill_constraint", v)}
                              >
                                <SelectTrigger><SelectValue /></SelectTrigger>
                                <SelectContent>
                                  {Object.entries(HILL_SLOPE_CONSTRAINT_LABELS).map(([v, l]) => (
                                    <SelectItem key={v} value={v}>{l}</SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="grid gap-1">
                              <Label className="text-xs">Normalization</Label>
                              <Select
                                value={rd.dr_normalization_scope}
                                onValueChange={(v) => updateReadout(index, "dr_normalization_scope", v)}
                              >
                                <SelectTrigger><SelectValue /></SelectTrigger>
                                <SelectContent>
                                  {Object.entries(NORMALIZATION_SCOPE_LABELS).map(([v, l]) => (
                                    <SelectItem key={v} value={v}>{l}</SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="grid gap-1">
                              <Label className="text-xs">Activity Threshold (%)</Label>
                              <Input
                                type="number"
                                min="0"
                                max="100"
                                placeholder="e.g., 30"
                                value={rd.dr_activity_threshold}
                                onChange={(e) =>
                                  updateReadout(index, "dr_activity_threshold", e.target.value)
                                }
                              />
                            </div>
                          </div>
                        </div>
                      )}
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

          <Separator />

          {/* Condition Definitions */}
          <div className="flex items-center justify-between">
            <Label className="text-base font-semibold">
              Conditions <span className="text-xs font-normal text-muted-foreground">(optional)</span>
            </Label>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setConditionDefs((prev) => [...prev, emptyConditionDef()])}
            >
              <Plus className="mr-2 h-4 w-4" />
              Add Condition
            </Button>
          </div>

          {conditionDefs.length > 0 && (
            <div className="space-y-2">
              {conditionDefs.map((cd, index) => (
                <div key={index} className="flex items-end gap-2">
                  <div className="grid gap-1 flex-1">
                    <Label className="text-xs">Name</Label>
                    <Input
                      placeholder="e.g., Cell Line"
                      value={cd.name}
                      onChange={(e) =>
                        setConditionDefs((prev) =>
                          prev.map((c, i) => (i === index ? { ...c, name: e.target.value } : c))
                        )
                      }
                    />
                  </div>
                  <div className="grid gap-1 w-[130px]">
                    <Label className="text-xs">Type</Label>
                    <Select
                      value={cd.data_type}
                      onValueChange={(v) =>
                        setConditionDefs((prev) =>
                          prev.map((c, i) => (i === index ? { ...c, data_type: v } : c))
                        )
                      }
                    >
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="text">Text</SelectItem>
                        <SelectItem value="numeric">Numeric</SelectItem>
                        <SelectItem value="pick_list">Pick List</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid gap-1 w-[100px]">
                    <Label className="text-xs">Unit</Label>
                    <Input
                      placeholder="optional"
                      value={cd.unit}
                      onChange={(e) =>
                        setConditionDefs((prev) =>
                          prev.map((c, i) => (i === index ? { ...c, unit: e.target.value } : c))
                        )
                      }
                    />
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="shrink-0"
                    onClick={() => setConditionDefs((prev) => prev.filter((_, i) => i !== index))}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              ))}
            </div>
          )}
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
