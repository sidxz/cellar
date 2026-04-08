"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Send,
  RotateCcw,
  Archive,
  Plus,
  Paperclip,
  Pencil,
  Trash2,
} from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import { StatusBadge } from "@/shared/components/status-badge";
import { Button } from "@/shared/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { Textarea } from "@/shared/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { FileUploadZone, AttachmentList } from "@/features/attachment";
import {
  useProtocol,
  usePublishProtocol,
  useRetireProtocol,
  useVersionProtocol,
  useUpdateProtocol,
  useDeleteProtocol,
  useAddReadoutDefinition,
  useRemoveReadoutDefinition,
  useAddConditionDefinition,
  useRemoveConditionDefinition,
  useSetControlLayout,
  useRemoveControlLayout,
  useSetOntologyAnnotation,
  useRemoveOntologyAnnotation,
} from "../hooks/use-protocols";
import { useOntologySlots } from "@/features/workspace-config/hooks/use-ontology-slots";
import {
  OntologySearchInput,
  type OntologyTerm,
} from "@/shared/components/ontology-search-input";
import { usePlateTemplates } from "../hooks/use-plate-templates";
import { ConditionGroupTable } from "./condition-group-table";
import { RunList } from "./run-list";
import { CreateRunDialog } from "./create-run-dialog";
import {
  CURVE_TYPE_LABELS,
  HILL_SLOPE_CONSTRAINT_LABELS,
  PLATE_FORMAT_LABELS,
  PROTOCOL_TYPE_LABELS,
  READOUT_AGGREGATION_LABELS,
  READOUT_DATA_TYPE_LABELS,
  READOUT_NORMALIZATION_LABELS,
  type CurveType,
  type HillSlopeConstraint,
  type PlateFormat,
  type ProtocolStatus,
  type ProtocolType,
  type ReadoutAggregation,
  type ReadoutDataType,
  type ReadoutNormalization,
} from "../types";

interface ProtocolDetailProps {
  protocolId: string;
}

export function ProtocolDetail({ protocolId }: ProtocolDetailProps) {
  const router = useRouter();
  const { data: protocol, isLoading } = useProtocol(protocolId);
  const publishMutation = usePublishProtocol();
  const retireMutation = useRetireProtocol();
  const versionMutation = useVersionProtocol();
  const updateMutation = useUpdateProtocol(protocolId);
  const deleteMutation = useDeleteProtocol();
  const addReadoutDef = useAddReadoutDefinition(protocolId);
  const removeReadoutDef = useRemoveReadoutDefinition(protocolId);
  const addConditionDef = useAddConditionDefinition(protocolId);
  const removeConditionDef = useRemoveConditionDefinition(protocolId);
  const setControlLayout = useSetControlLayout(protocolId);
  const removeControlLayout = useRemoveControlLayout(protocolId);
  const setOntologyAnnotation = useSetOntologyAnnotation(protocolId);
  const removeOntologyAnnotation = useRemoveOntologyAnnotation(protocolId);
  const { data: plateTemplates } = usePlateTemplates();
  const { data: ontologySlots } = useOntologySlots();
  const [createRunOpen, setCreateRunOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [addReadoutOpen, setAddReadoutOpen] = useState(false);
  const [addConditionOpen, setAddConditionOpen] = useState(false);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editCategory, setEditCategory] = useState("");
  const [rdName, setRdName] = useState("");
  const [rdDataType, setRdDataType] = useState("numeric");
  const [rdUnit, setRdUnit] = useState("");
  const [rdAggregation, setRdAggregation] = useState("none");
  const [rdNormalization, setRdNormalization] = useState("none");
  // Condition definition form state
  const [cdName, setCdName] = useState("");
  const [cdDataType, setCdDataType] = useState("text");
  const [cdUnit, setCdUnit] = useState("");
  // Control layout form state
  const [clFormat, setClFormat] = useState("96");
  const [clTemplateId, setClTemplateId] = useState("");

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (!protocol) {
    return (
      <div className="text-center text-muted-foreground py-12">
        Protocol not found.
      </div>
    );
  }

  const status = protocol.status as ProtocolStatus;

  return (
    <div className="space-y-6">
      {/* Back button */}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => router.back()}
      >
        <ArrowLeft className="mr-2 h-4 w-4" />
        Back
      </Button>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight">
              {protocol.name}
            </h1>
            <StatusBadge status={status} />
            <Badge variant="outline" className="font-mono">
              v{protocol.protocol_version}
            </Badge>
          </div>
          {protocol.description && (
            <p className="mt-1 text-muted-foreground">
              {protocol.description}
            </p>
          )}
        </div>

        <div className="flex items-center gap-2">
          {status === "draft" && (
            <>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setEditName(protocol.name);
                  setEditDescription(protocol.description ?? "");
                  setEditCategory(protocol.category ?? "");
                  setEditOpen(true);
                }}
              >
                <Pencil className="mr-2 h-4 w-4" />
                Edit
              </Button>
              <Button
                size="sm"
                variant="destructive"
                onClick={() => setDeleteOpen(true)}
              >
                <Trash2 className="mr-2 h-4 w-4" />
                Delete
              </Button>
              <Button
                size="sm"
                onClick={() => publishMutation.mutate(protocolId)}
                disabled={publishMutation.isPending}
              >
                <Send className="mr-2 h-4 w-4" />
                {publishMutation.isPending ? "Publishing..." : "Publish"}
              </Button>
            </>
          )}
          {status === "active" && (
            <>
              <Button
                size="sm"
                variant="outline"
                onClick={() => versionMutation.mutate(protocolId)}
                disabled={versionMutation.isPending}
              >
                <RotateCcw className="mr-2 h-4 w-4" />
                {versionMutation.isPending ? "Creating..." : "New Version"}
              </Button>
              <Button
                size="sm"
                variant="destructive"
                onClick={() =>
                  retireMutation.mutate({
                    id: protocolId,
                    reason: "Retired by user",
                  })
                }
                disabled={retireMutation.isPending}
              >
                <Archive className="mr-2 h-4 w-4" />
                {retireMutation.isPending ? "Retiring..." : "Retire"}
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Metadata */}
      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div>
              <p className="text-sm text-muted-foreground">Type</p>
              <p className="font-medium">
                {PROTOCOL_TYPE_LABELS[
                  protocol.protocol_type as ProtocolType
                ] ?? protocol.protocol_type}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Category</p>
              <p className="font-medium">{protocol.category ?? "\u2014"}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Version</p>
              <p className="font-medium">{protocol.protocol_version}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Readouts</p>
              <p className="font-medium">
                {protocol.readout_definitions.length}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Ontology Annotations */}
      {ontologySlots && ontologySlots.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Ontology Annotations</CardTitle>
            <CardDescription>
              Controlled vocabulary terms linked to this protocol.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {ontologySlots.map((slot) => {
                // ontology_annotations is a dict keyed by slot name, e.g. { "bioassay_type": [...] }
                const rawTerms = protocol.ontology_annotations?.[slot.name] ?? [];
                const currentTerms: OntologyTerm[] = rawTerms.map((t) => ({
                  term_id: t.term_id,
                  label: t.label,
                  ontology_source: t.ontology_source,
                  uri: t.uri ?? null,
                }));
                return (
                  <div key={slot.id} className="grid gap-1.5">
                    <Label className="text-sm font-medium">
                      {slot.label}
                      {slot.is_required && (
                        <span className="ml-1 text-destructive">*</span>
                      )}
                    </Label>
                    {status === "draft" ? (
                      <OntologySearchInput
                        ontologySources={slot.ontology_sources}
                        rootConceptId={slot.root_concept_id}
                        value={currentTerms}
                        onChange={(terms) => {
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
                        allowFreeText={slot.allow_free_text}
                        placeholder={`Search ${slot.ontology_sources.join(", ")} terms...`}
                      />
                    ) : currentTerms.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {currentTerms.map((term) => (
                          <Badge key={term.term_id} variant="secondary">
                            {term.label}
                            <span className="ml-1 text-[10px] text-muted-foreground">
                              ({term.ontology_source})
                            </span>
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
            </div>
          </CardContent>
        </Card>
      )}

      {/* Readout Definitions */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Readout Definitions</CardTitle>
            <CardDescription>
              Data points collected in each run.
            </CardDescription>
          </div>
          {status === "draft" && (
            <Button size="sm" variant="outline" onClick={() => setAddReadoutOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              Add Readout
            </Button>
          )}
        </CardHeader>
        <CardContent>
          {protocol.readout_definitions.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No readout definitions.
            </p>
          ) : (
            <div className="rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-12">#</TableHead>
                    <TableHead>Name</TableHead>
                    <TableHead>Data Type</TableHead>
                    <TableHead>Unit</TableHead>
                    <TableHead>Aggregation</TableHead>
                    <TableHead>Normalization</TableHead>
                    {status === "draft" && <TableHead className="w-12" />}
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
                          <span className="block text-xs text-muted-foreground mt-0.5">
                            {rd.dose_response_config.x_readout_name} / {rd.dose_response_config.y_readout_name}
                          </span>
                        )}
                        {rd.pick_list_values && rd.pick_list_values.length > 0 && (
                          <span className="block text-xs text-muted-foreground mt-0.5">
                            Values: {rd.pick_list_values.join(", ")}
                          </span>
                        )}
                      </TableCell>
                      <TableCell>
                        {READOUT_DATA_TYPE_LABELS[
                          rd.data_type as ReadoutDataType
                        ] ?? rd.data_type}
                        {rd.dose_response_config && (
                          <span className="block text-xs text-muted-foreground">
                            {CURVE_TYPE_LABELS[rd.dose_response_config.curve_type as CurveType] ?? rd.dose_response_config.curve_type}
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
                      {status === "draft" && (
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                            onClick={() => removeReadoutDef.mutate(rd.id)}
                            disabled={removeReadoutDef.isPending || protocol.readout_definitions.length <= 1}
                            title={protocol.readout_definitions.length <= 1 ? "Cannot remove last readout definition" : "Remove"}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </TableCell>
                      )}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Condition Definitions */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Condition Definitions</CardTitle>
            <CardDescription>
              Experimental conditions tracked per run.
            </CardDescription>
          </div>
          {status === "draft" && (
            <Button size="sm" variant="outline" onClick={() => setAddConditionOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              Add Condition
            </Button>
          )}
        </CardHeader>
        <CardContent>
          {protocol.condition_definitions.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No condition definitions.
            </p>
          ) : (
            <div className="rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Data Type</TableHead>
                    <TableHead>Unit</TableHead>
                    {status === "draft" && <TableHead className="w-12" />}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {protocol.condition_definitions.map((cd) => (
                    <TableRow key={cd.id}>
                      <TableCell className="font-medium">{cd.name}</TableCell>
                      <TableCell>{cd.data_type}</TableCell>
                      <TableCell>{cd.unit ?? "\u2014"}</TableCell>
                      {status === "draft" && (
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                            onClick={() => removeConditionDef.mutate(cd.id)}
                            disabled={removeConditionDef.isPending}
                            title="Remove"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </TableCell>
                      )}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Control Layouts */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Control Layouts</CardTitle>
            <CardDescription>
              Default plate templates per format.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          {protocol.control_layouts && Object.keys(protocol.control_layouts).length > 0 ? (
            <div className="space-y-2">
              {Object.entries(protocol.control_layouts).map(([format, templateId]) => {
                const tpl = plateTemplates?.find((t) => t.id === templateId);
                return (
                  <div key={format} className="flex items-center justify-between rounded-lg border p-3">
                    <div>
                      <span className="font-medium">{PLATE_FORMAT_LABELS[format as PlateFormat] ?? format}</span>
                      <span className="mx-2 text-muted-foreground">&rarr;</span>
                      <span>{tpl?.name ?? templateId}</span>
                    </div>
                    {status === "draft" && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                        onClick={() => removeControlLayout.mutate(format)}
                        disabled={removeControlLayout.isPending}
                        title="Remove"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground mb-4">
              No control layouts configured.
            </p>
          )}
          {status === "draft" && plateTemplates && plateTemplates.length > 0 && (
            <div className="flex items-end gap-2 mt-4">
              <div className="grid gap-1.5">
                <Label className="text-xs">Format</Label>
                <Select value={clFormat} onValueChange={setClFormat}>
                  <SelectTrigger className="w-[120px]"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.entries(PLATE_FORMAT_LABELS).map(([v, l]) => (
                      <SelectItem key={v} value={v}>{l}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-1.5 flex-1">
                <Label className="text-xs">Template</Label>
                <Select value={clTemplateId} onValueChange={setClTemplateId}>
                  <SelectTrigger><SelectValue placeholder="Select template..." /></SelectTrigger>
                  <SelectContent>
                    {plateTemplates.map((tpl) => (
                      <SelectItem key={tpl.id} value={tpl.id}>{tpl.name} ({PLATE_FORMAT_LABELS[tpl.format as PlateFormat] ?? tpl.format})</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button
                size="sm"
                onClick={() => {
                  if (clTemplateId) {
                    setControlLayout.mutate(
                      { plate_format: clFormat, template_id: clTemplateId },
                      { onSuccess: () => setClTemplateId("") }
                    );
                  }
                }}
                disabled={!clTemplateId || setControlLayout.isPending}
              >
                Set Layout
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Condition Grouping */}
      {protocol.condition_definitions.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Condition Grouping</CardTitle>
            <CardDescription>
              Readout values aggregated by experimental condition across runs.
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

      {/* Runs */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Runs</h2>
          {status === "active" && (
            <Button size="sm" onClick={() => setCreateRunOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              New Run
            </Button>
          )}
        </div>
        <RunList
          protocolId={protocolId}
          onSelect={(runId) => {
            router.push(`/assays/runs/${runId}`);
          }}
        />
      </div>

      {/* Files */}
      <div>
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <Paperclip className="h-4 w-4" />
          Files
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Attachments associated with this protocol.
        </p>
        <div className="mt-4 space-y-6">
          <FileUploadZone entityType="protocol" entityId={protocolId} />
          <AttachmentList entityType="protocol" entityId={protocolId} />
        </div>
      </div>

      <CreateRunDialog
        protocolId={protocolId}
        open={createRunOpen}
        onOpenChange={setCreateRunOpen}
      />

      {/* Edit Draft Dialog */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Protocol</DialogTitle>
            <DialogDescription>
              Update this draft protocol&apos;s metadata.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label>Name</Label>
              <Input
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label>Description</Label>
              <Textarea
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
                placeholder="Optional — describe the assay procedure, controls, and acceptance criteria"
                rows={4}
              />
            </div>
            <div className="grid gap-2">
              <Label>Category</Label>
              <Input
                value={editCategory}
                onChange={(e) => setEditCategory(e.target.value)}
                placeholder="Optional"
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={() => {
                updateMutation.mutate(
                  {
                    name: editName || undefined,
                    description: editDescription || null,
                    category: editCategory || null,
                  },
                  { onSuccess: () => setEditOpen(false) }
                );
              }}
              disabled={!editName.trim() || updateMutation.isPending}
            >
              {updateMutation.isPending ? "Saving..." : "Save Changes"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Draft Protocol</DialogTitle>
            <DialogDescription>
              This will permanently delete &quot;{protocol.name}&quot; (v{protocol.protocol_version}).
              This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                deleteMutation.mutate(protocolId, {
                  onSuccess: () => {
                    router.push("/assays");
                  },
                });
              }}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? "Deleting..." : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Add Condition Definition Dialog */}
      <Dialog open={addConditionOpen} onOpenChange={setAddConditionOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Condition Definition</DialogTitle>
            <DialogDescription>
              Define an experimental condition for categorizing runs.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label>Name</Label>
              <Input
                value={cdName}
                onChange={(e) => setCdName(e.target.value)}
                placeholder="e.g., Cell Line, Species, Time Point"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label>Data Type</Label>
                <Select value={cdDataType} onValueChange={setCdDataType}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="text">Text</SelectItem>
                    <SelectItem value="numeric">Numeric</SelectItem>
                    <SelectItem value="pick_list">Pick List</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label>Unit</Label>
                <Input
                  value={cdUnit}
                  onChange={(e) => setCdUnit(e.target.value)}
                  placeholder="Optional"
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={() => {
                addConditionDef.mutate(
                  {
                    name: cdName,
                    data_type: cdDataType,
                    unit: cdUnit || undefined,
                  },
                  {
                    onSuccess: () => {
                      setAddConditionOpen(false);
                      setCdName("");
                      setCdDataType("text");
                      setCdUnit("");
                    },
                  }
                );
              }}
              disabled={!cdName.trim() || addConditionDef.isPending}
            >
              {addConditionDef.isPending ? "Adding..." : "Add Condition"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Add Readout Definition Dialog */}
      <Dialog open={addReadoutOpen} onOpenChange={setAddReadoutOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Readout Definition</DialogTitle>
            <DialogDescription>
              Define a new measurement column for this protocol.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label>Name</Label>
              <Input
                value={rdName}
                onChange={(e) => setRdName(e.target.value)}
                placeholder="e.g., % Inhibition, IC50, Fluorescence"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label>Data Type</Label>
                <Select value={rdDataType} onValueChange={setRdDataType}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.entries(READOUT_DATA_TYPE_LABELS).map(([v, l]) => (
                      <SelectItem key={v} value={v}>{l}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label>Unit</Label>
                <Input
                  value={rdUnit}
                  onChange={(e) => setRdUnit(e.target.value)}
                  placeholder="e.g., %, nM, RFU"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label>Aggregation</Label>
                <Select value={rdAggregation} onValueChange={setRdAggregation}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.entries(READOUT_AGGREGATION_LABELS).map(([v, l]) => (
                      <SelectItem key={v} value={v}>{l}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label>Normalization</Label>
                <Select value={rdNormalization} onValueChange={setRdNormalization}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.entries(READOUT_NORMALIZATION_LABELS).map(([v, l]) => (
                      <SelectItem key={v} value={v}>{l}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={() => {
                addReadoutDef.mutate(
                  {
                    name: rdName,
                    data_type: rdDataType,
                    unit: rdUnit || undefined,
                    aggregation: rdAggregation,
                    normalization: rdNormalization,
                  },
                  {
                    onSuccess: () => {
                      setAddReadoutOpen(false);
                      setRdName("");
                      setRdDataType("numeric");
                      setRdUnit("");
                      setRdAggregation("none");
                      setRdNormalization("none");
                    },
                  }
                );
              }}
              disabled={!rdName.trim() || addReadoutDef.isPending}
            >
              {addReadoutDef.isPending ? "Adding..." : "Add Readout"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
