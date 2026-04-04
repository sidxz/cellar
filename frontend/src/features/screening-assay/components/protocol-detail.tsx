"use client";

import { useState } from "react";
import {
  ArrowLeft,
  Send,
  RotateCcw,
  Archive,
  Plus,
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
import { Skeleton } from "@/shared/components/ui/skeleton";
import {
  useProtocol,
  usePublishProtocol,
  useRetireProtocol,
  useVersionProtocol,
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
  const [createRunOpen, setCreateRunOpen] = useState(false);

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
            <Button
              size="sm"
              onClick={() => publishMutation.mutate(protocolId)}
              disabled={publishMutation.isPending}
            >
              <Send className="mr-2 h-4 w-4" />
              {publishMutation.isPending ? "Publishing..." : "Publish"}
            </Button>
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
        <CardHeader>
          <CardTitle>Readout Definitions</CardTitle>
          <CardDescription>
            Data points collected in each run.
          </CardDescription>
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
    </div>
  );
}
