"use client";

import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import {
  useAddReadoutDefinition,
  useRemoveReadoutDefinition,
  useAddConditionDefinition,
  useRemoveConditionDefinition,
  useSetControlLayout,
  useRemoveControlLayout,
  useSetOntologyAnnotation,
  useRemoveOntologyAnnotation,
} from "../../hooks/use-protocols";
import { useOntologySlots } from "@/features/workspace-config/hooks/use-ontology-slots";
import {
  OntologySearchInput,
  type OntologyTerm,
} from "@/shared/components/ontology-search-input";
import { usePlateTemplates } from "../../hooks/use-plate-templates";
import { ConditionGroupTable } from "../condition-group-table";
import {
  CURVE_TYPE_LABELS,
  PLATE_FORMAT_LABELS,
  READOUT_AGGREGATION_LABELS,
  READOUT_DATA_TYPE_LABELS,
  READOUT_NORMALIZATION_LABELS,
  type CurveType,
  type PlateFormat,
  type Protocol,
  type ProtocolStatus,
  type ReadoutAggregation,
  type ReadoutDataType,
  type ReadoutNormalization,
} from "../../types";

// ---------------------------------------------------------------------------
// DesignTab
// ---------------------------------------------------------------------------

interface DesignTabProps {
  protocol: Protocol;
  protocolId: string;
}

export function DesignTab({ protocol, protocolId }: DesignTabProps) {
  const status = protocol.status as ProtocolStatus;
  const isDraft = status === "draft";

  // --- Mutations ---
  const addReadoutDef = useAddReadoutDefinition(protocolId);
  const removeReadoutDef = useRemoveReadoutDefinition(protocolId);
  const addConditionDef = useAddConditionDefinition(protocolId);
  const removeConditionDef = useRemoveConditionDefinition(protocolId);
  const setControlLayout = useSetControlLayout(protocolId);
  const removeControlLayout = useRemoveControlLayout(protocolId);
  const setOntologyAnnotation = useSetOntologyAnnotation(protocolId);
  const removeOntologyAnnotation = useRemoveOntologyAnnotation(protocolId);

  // --- Queries ---
  const { data: plateTemplates } = usePlateTemplates();
  const { data: ontologySlots } = useOntologySlots();

  // --- Dialog state ---
  const [addReadoutOpen, setAddReadoutOpen] = useState(false);
  const [addConditionOpen, setAddConditionOpen] = useState(false);

  // --- Readout form fields ---
  const [rdName, setRdName] = useState("");
  const [rdDataType, setRdDataType] = useState("numeric");
  const [rdUnit, setRdUnit] = useState("");
  const [rdAggregation, setRdAggregation] = useState("none");
  const [rdNormalization, setRdNormalization] = useState("none");

  // --- Condition form fields ---
  const [cdName, setCdName] = useState("");
  const [cdDataType, setCdDataType] = useState("text");
  const [cdUnit, setCdUnit] = useState("");

  // --- Control layout form fields ---
  const [clFormat, setClFormat] = useState("96");
  const [clTemplateId, setClTemplateId] = useState("");

  return (
    <div className="space-y-6">
      {/* ── 1. Ontology Annotations ─────────────────────────────────────── */}
      {ontologySlots && ontologySlots.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Ontology Annotations</CardTitle>
            <CardDescription>
              Controlled vocabulary terms for this protocol.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {ontologySlots.map((slot) => {
              const currentTerms =
                protocol.ontology_annotations?.[slot.name] ?? [];
              return (
                <div key={slot.id} className="space-y-1">
                  <Label className="text-sm font-medium">
                    {slot.label}
                    {slot.is_required && (
                      <span className="ml-1 text-destructive">*</span>
                    )}
                  </Label>

                  {isDraft ? (
                    <OntologySearchInput
                      ontologySources={slot.ontology_sources}
                      rootConceptId={slot.root_concept_id}
                      allowFreeText={slot.allow_free_text}
                      value={currentTerms.map((t) => ({
                        term_id: t.term_id,
                        label: t.label,
                        ontology_source: t.ontology_source,
                        uri: t.uri,
                      }))}
                      onChange={(terms: OntologyTerm[]) => {
                        if (terms.length === 0) {
                          removeOntologyAnnotation.mutate(slot.name);
                        } else {
                          setOntologyAnnotation.mutate({
                            slot: slot.name,
                            terms: terms.map((t) => ({
                              term_id: t.term_id,
                              label: t.label,
                              ontology_source: t.ontology_source,
                              uri: t.uri,
                            })),
                          });
                        }
                      }}
                    />
                  ) : currentTerms.length > 0 ? (
                    <div className="flex flex-wrap gap-1">
                      {currentTerms.map((t) => (
                        <Badge key={t.term_id} variant="secondary">
                          {t.label}
                        </Badge>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      No terms assigned.
                    </p>
                  )}
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      {/* ── 2. Readout Definitions ──────────────────────────────────────── */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Readout Definitions</CardTitle>
            <CardDescription>
              Measured values captured for each compound in a run.
            </CardDescription>
          </div>
          {isDraft && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setAddReadoutOpen(true)}
            >
              <Plus className="mr-1 h-4 w-4" />
              Add
            </Button>
          )}
        </CardHeader>
        <CardContent>
          {protocol.readout_definitions.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No readout definitions yet.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">#</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Data Type</TableHead>
                  <TableHead>Unit</TableHead>
                  <TableHead>Aggregation</TableHead>
                  <TableHead>Normalization</TableHead>
                  {isDraft && <TableHead className="w-10" />}
                </TableRow>
              </TableHeader>
              <TableBody>
                {protocol.readout_definitions.map((rd, idx) => (
                  <TableRow key={rd.id}>
                    <TableCell className="text-muted-foreground">
                      {idx + 1}
                    </TableCell>
                    <TableCell>
                      <span className="font-medium">{rd.name}</span>
                      {rd.dose_response_config && (
                        <span className="ml-2 text-xs text-muted-foreground">
                          (
                          {
                            CURVE_TYPE_LABELS[
                              rd.dose_response_config
                                .curve_type as CurveType
                            ]
                          }
                          : {rd.dose_response_config.x_readout_name} vs{" "}
                          {rd.dose_response_config.y_readout_name})
                        </span>
                      )}
                      {rd.pick_list_values &&
                        rd.pick_list_values.length > 0 && (
                          <div className="mt-0.5 flex flex-wrap gap-1">
                            {rd.pick_list_values.map((v) => (
                              <Badge
                                key={v}
                                variant="outline"
                                className="text-[10px]"
                              >
                                {v}
                              </Badge>
                            ))}
                          </div>
                        )}
                    </TableCell>
                    <TableCell>
                      {READOUT_DATA_TYPE_LABELS[
                        rd.data_type as ReadoutDataType
                      ] ?? rd.data_type}
                      {rd.dose_response_config && (
                        <span className="ml-1 text-xs text-muted-foreground">
                          (
                          {
                            CURVE_TYPE_LABELS[
                              rd.dose_response_config
                                .curve_type as CurveType
                            ]
                          }
                          )
                        </span>
                      )}
                    </TableCell>
                    <TableCell>{rd.unit ?? "\u2014"}</TableCell>
                    <TableCell>
                      {READOUT_AGGREGATION_LABELS[
                        rd.aggregation as ReadoutAggregation
                      ] ?? rd.aggregation}
                    </TableCell>
                    <TableCell>
                      {READOUT_NORMALIZATION_LABELS[
                        rd.normalization as ReadoutNormalization
                      ] ?? rd.normalization}
                    </TableCell>
                    {isDraft && (
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-destructive hover:text-destructive"
                          disabled={
                            protocol.readout_definitions.length <= 1
                          }
                          onClick={() =>
                            removeReadoutDef.mutate(rd.id)
                          }
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* ── 3. Condition Definitions ────────────────────────────────────── */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Condition Definitions</CardTitle>
            <CardDescription>
              Experimental conditions that vary between runs.
            </CardDescription>
          </div>
          {isDraft && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setAddConditionOpen(true)}
            >
              <Plus className="mr-1 h-4 w-4" />
              Add
            </Button>
          )}
        </CardHeader>
        <CardContent>
          {protocol.condition_definitions.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No condition definitions yet.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Data Type</TableHead>
                  <TableHead>Unit</TableHead>
                  {isDraft && <TableHead className="w-10" />}
                </TableRow>
              </TableHeader>
              <TableBody>
                {protocol.condition_definitions.map((cd) => (
                  <TableRow key={cd.id}>
                    <TableCell className="font-medium">{cd.name}</TableCell>
                    <TableCell className="capitalize">
                      {cd.data_type}
                    </TableCell>
                    <TableCell>{cd.unit ?? "\u2014"}</TableCell>
                    {isDraft && (
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-destructive hover:text-destructive"
                          onClick={() =>
                            removeConditionDef.mutate(cd.id)
                          }
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* ── 4. Control Layouts ──────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle>Control Layouts</CardTitle>
          <CardDescription>
            Plate templates for positive/negative controls per plate format.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Existing layouts */}
          {protocol.control_layouts &&
          Object.keys(protocol.control_layouts).length > 0 ? (
            <div className="space-y-2">
              {Object.entries(protocol.control_layouts).map(
                ([format, templateId]) => {
                  const tmpl = plateTemplates?.find(
                    (pt) => pt.id === templateId,
                  );
                  return (
                    <div
                      key={format}
                      className="flex items-center justify-between rounded-md border px-3 py-2"
                    >
                      <span className="text-sm">
                        {PLATE_FORMAT_LABELS[format as PlateFormat] ??
                          `${format}-well`}{" "}
                        &rarr;{" "}
                        <span className="font-medium">
                          {tmpl?.name ?? templateId}
                        </span>
                      </span>
                      {isDraft && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-destructive hover:text-destructive"
                          onClick={() =>
                            removeControlLayout.mutate(format)
                          }
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  );
                },
              )}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              No control layouts configured.
            </p>
          )}

          {/* Add form (draft only) */}
          {isDraft && (
            <div className="flex items-end gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Format</Label>
                <Select value={clFormat} onValueChange={setClFormat}>
                  <SelectTrigger className="w-[120px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(PLATE_FORMAT_LABELS).map(
                      ([val, label]) => (
                        <SelectItem key={val} value={val}>
                          {label}
                        </SelectItem>
                      ),
                    )}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Template</Label>
                <Select
                  value={clTemplateId}
                  onValueChange={setClTemplateId}
                >
                  <SelectTrigger className="w-[200px]">
                    <SelectValue placeholder="Select template..." />
                  </SelectTrigger>
                  <SelectContent>
                    {(plateTemplates ?? []).map((pt) => (
                      <SelectItem key={pt.id} value={pt.id}>
                        {pt.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button
                size="sm"
                disabled={!clTemplateId}
                onClick={() => {
                  setControlLayout.mutate(
                    {
                      plate_format: clFormat,
                      template_id: clTemplateId,
                    },
                    {
                      onSuccess: () => {
                        setClTemplateId("");
                      },
                    },
                  );
                }}
              >
                Set Layout
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── 5. Condition Grouping ───────────────────────────────────────── */}
      {protocol.condition_definitions.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Condition Grouping</CardTitle>
            <CardDescription>
              Aggregated readout values grouped by experimental condition.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ConditionGroupTable
              protocolId={protocolId}
              conditionDefinitions={protocol.condition_definitions}
            />
          </CardContent>
        </Card>
      )}

      {/* ── Add Readout Definition Dialog ───────────────────────────────── */}
      <Dialog open={addReadoutOpen} onOpenChange={setAddReadoutOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Readout Definition</DialogTitle>
            <DialogDescription>
              Define a new measured value for this protocol.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1">
              <Label>Name</Label>
              <Input
                value={rdName}
                onChange={(e) => setRdName(e.target.value)}
                placeholder="e.g. % Inhibition"
              />
            </div>
            <div className="space-y-1">
              <Label>Data Type</Label>
              <Select value={rdDataType} onValueChange={setRdDataType}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(READOUT_DATA_TYPE_LABELS).map(
                    ([val, label]) => (
                      <SelectItem key={val} value={val}>
                        {label}
                      </SelectItem>
                    ),
                  )}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Unit</Label>
              <Input
                value={rdUnit}
                onChange={(e) => setRdUnit(e.target.value)}
                placeholder="e.g. nM, %, \u00B5M"
              />
            </div>
            <div className="space-y-1">
              <Label>Aggregation</Label>
              <Select
                value={rdAggregation}
                onValueChange={setRdAggregation}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(READOUT_AGGREGATION_LABELS).map(
                    ([val, label]) => (
                      <SelectItem key={val} value={val}>
                        {label}
                      </SelectItem>
                    ),
                  )}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Normalization</Label>
              <Select
                value={rdNormalization}
                onValueChange={setRdNormalization}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(READOUT_NORMALIZATION_LABELS).map(
                    ([val, label]) => (
                      <SelectItem key={val} value={val}>
                        {label}
                      </SelectItem>
                    ),
                  )}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setAddReadoutOpen(false)}
            >
              Cancel
            </Button>
            <Button
              disabled={!rdName.trim() || addReadoutDef.isPending}
              onClick={() => {
                addReadoutDef.mutate(
                  {
                    name: rdName.trim(),
                    data_type: rdDataType,
                    unit: rdUnit.trim() || undefined,
                    aggregation: rdAggregation,
                    normalization: rdNormalization,
                  },
                  {
                    onSuccess: () => {
                      setRdName("");
                      setRdDataType("numeric");
                      setRdUnit("");
                      setRdAggregation("none");
                      setRdNormalization("none");
                      setAddReadoutOpen(false);
                    },
                  },
                );
              }}
            >
              {addReadoutDef.isPending ? "Adding..." : "Add"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Add Condition Definition Dialog ─────────────────────────────── */}
      <Dialog open={addConditionOpen} onOpenChange={setAddConditionOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Condition Definition</DialogTitle>
            <DialogDescription>
              Define an experimental condition that varies between runs.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1">
              <Label>Name</Label>
              <Input
                value={cdName}
                onChange={(e) => setCdName(e.target.value)}
                placeholder="e.g. Cell Passage, Temperature"
              />
            </div>
            <div className="space-y-1">
              <Label>Data Type</Label>
              <Select value={cdDataType} onValueChange={setCdDataType}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="text">Text</SelectItem>
                  <SelectItem value="numeric">Numeric</SelectItem>
                  <SelectItem value="pick_list">Pick List</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Unit</Label>
              <Input
                value={cdUnit}
                onChange={(e) => setCdUnit(e.target.value)}
                placeholder="e.g. \u00B0C, hrs"
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setAddConditionOpen(false)}
            >
              Cancel
            </Button>
            <Button
              disabled={!cdName.trim() || addConditionDef.isPending}
              onClick={() => {
                addConditionDef.mutate(
                  {
                    name: cdName.trim(),
                    data_type: cdDataType,
                    unit: cdUnit.trim() || undefined,
                  },
                  {
                    onSuccess: () => {
                      setCdName("");
                      setCdDataType("text");
                      setCdUnit("");
                      setAddConditionOpen(false);
                    },
                  },
                );
              }}
            >
              {addConditionDef.isPending ? "Adding..." : "Add"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
