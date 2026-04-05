"use client";

import { useState } from "react";
import {
  ArrowLeft,
  Send,
  RotateCcw,
  Archive,
  Plus,
  Pencil,
  Trash2,
} from "lucide-react";
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
import {
  useProtocol,
  usePublishProtocol,
  useRetireProtocol,
  useVersionProtocol,
  useUpdateProtocol,
  useDeleteProtocol,
  useAddReadoutDefinition,
  useRemoveReadoutDefinition,
} from "../hooks/use-protocols";
import { RunList } from "./run-list";
import { CreateRunDialog } from "./create-run-dialog";
import {
  PROTOCOL_TYPE_LABELS,
  READOUT_AGGREGATION_LABELS,
  READOUT_DATA_TYPE_LABELS,
  READOUT_NORMALIZATION_LABELS,
  type ProtocolStatus,
  type ProtocolType,
  type ReadoutAggregation,
  type ReadoutDataType,
  type ReadoutNormalization,
} from "../types";

interface ProtocolDetailProps {
  protocolId: string;
}

function statusBadgeVariant(
  status: ProtocolStatus
): "default" | "outline" | "destructive" {
  switch (status) {
    case "active":
      return "default";
    case "draft":
      return "outline";
    case "retired":
      return "destructive";
  }
}

export function ProtocolDetail({ protocolId }: ProtocolDetailProps) {
  const { data: protocol, isLoading } = useProtocol(protocolId);
  const publishMutation = usePublishProtocol();
  const retireMutation = useRetireProtocol();
  const versionMutation = useVersionProtocol();
  const updateMutation = useUpdateProtocol(protocolId);
  const deleteMutation = useDeleteProtocol();
  const addReadoutDef = useAddReadoutDefinition(protocolId);
  const removeReadoutDef = useRemoveReadoutDefinition(protocolId);
  const [createRunOpen, setCreateRunOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [addReadoutOpen, setAddReadoutOpen] = useState(false);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editCategory, setEditCategory] = useState("");
  const [rdName, setRdName] = useState("");
  const [rdDataType, setRdDataType] = useState("numeric");
  const [rdUnit, setRdUnit] = useState("");
  const [rdAggregation, setRdAggregation] = useState("none");
  const [rdNormalization, setRdNormalization] = useState("none");

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
        onClick={() => window.history.back()}
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
            <Badge variant={statusBadgeVariant(status)}>{status}</Badge>
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
                      <TableCell className="font-medium">{rd.name}</TableCell>
                      <TableCell>
                        {READOUT_DATA_TYPE_LABELS[
                          rd.data_type as ReadoutDataType
                        ] ?? rd.data_type}
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
      {protocol.condition_definitions.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Condition Definitions</CardTitle>
            <CardDescription>
              Experimental conditions tracked per run.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Data Type</TableHead>
                    <TableHead>Unit</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {protocol.condition_definitions.map((cd) => (
                    <TableRow key={cd.id}>
                      <TableCell className="font-medium">{cd.name}</TableCell>
                      <TableCell>{cd.data_type}</TableCell>
                      <TableCell>{cd.unit ?? "\u2014"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
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
            window.location.href = `/assays/runs/${runId}`;
          }}
        />
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
                    window.location.href = "/assays";
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
