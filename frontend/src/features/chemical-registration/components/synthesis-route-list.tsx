"use client";

import { useMemo, useState } from "react";
import { GitBranch, Plus } from "lucide-react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { EmptyState, ErrorState } from "@/shared/components/empty-state";
import {
  Dialog,
  DialogContent,
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
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import {
  useSynthesisRoutesByMolecule,
  useCreateSynthesisRoute,
} from "../hooks/use-synthesis-routes";
import {
  ROUTE_STATUS_LABELS,
  ROUTE_TYPE_LABELS,
  ROUTE_SCALE_LABELS,
  type RouteStatus,
  type SynthesisRouteSummary,
} from "../types/synthesis-route";
import { SynthesisRouteDetail } from "./synthesis-route-detail";

// ---------------------------------------------------------------------------
// Badge helpers
// ---------------------------------------------------------------------------

function routeStatusVariant(
  s: RouteStatus
): "default" | "secondary" | "destructive" | "outline" {
  switch (s) {
    case "preferred":
      return "default";
    case "validated":
      return "secondary";
    case "deprecated":
      return "destructive";
    default:
      return "outline"; // draft
  }
}

// ---------------------------------------------------------------------------
// Create Route Dialog
// ---------------------------------------------------------------------------

interface CreateRouteDialogProps {
  moleculeId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function CreateRouteDialog({
  moleculeId,
  open,
  onOpenChange,
}: CreateRouteDialogProps) {
  const createMutation = useCreateSynthesisRoute();

  const [name, setName] = useState("");
  const [routeType, setRouteType] = useState("linear");
  const [source, setSource] = useState("in_house");
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setName("");
    setRouteType("linear");
    setSource("in_house");
    setError(null);
  };

  const handleSubmit = async () => {
    setError(null);
    if (!name.trim()) {
      setError("Name is required");
      return;
    }
    try {
      await createMutation.mutateAsync({
        target_molecule_id: moleculeId,
        name: name.trim(),
        route_type: routeType,
        source,
      });
      reset();
      onOpenChange(false);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to create route";
      setError(message);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) reset();
        onOpenChange(v);
      }}
    >
      <DialogContent className="sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle>New Synthesis Route</DialogTitle>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="route-name">Name</Label>
            <Input
              id="route-name"
              placeholder="e.g. Route A — Buchwald coupling"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="route-type">Route Type</Label>
            <Select value={routeType} onValueChange={setRouteType}>
              <SelectTrigger id="route-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(ROUTE_TYPE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="route-source">Source</Label>
            <Select value={source} onValueChange={setSource}>
              <SelectTrigger id="route-source">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="in_house">In House</SelectItem>
                <SelectItem value="literature">Literature</SelectItem>
                <SelectItem value="vendor">Vendor</SelectItem>
                <SelectItem value="patent">Patent</SelectItem>
                <SelectItem value="ai_generated">AI Generated</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={createMutation.isPending}
          >
            {createMutation.isPending ? "Creating..." : "Create Route"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// SynthesisRouteList
// ---------------------------------------------------------------------------

interface SynthesisRouteListProps {
  moleculeId: string;
}

export function SynthesisRouteList({ moleculeId }: SynthesisRouteListProps) {
  const { data: routes, isLoading, error } = useSynthesisRoutesByMolecule(moleculeId);
  const [createOpen, setCreateOpen] = useState(false);
  const [selectedRouteId, setSelectedRouteId] = useState<string | null>(null);

  const columnDefs = useMemo<ColDef<SynthesisRouteSummary>[]>(
    () => [
      { headerName: "Name", field: "name", flex: 1, minWidth: 160 },
      {
        headerName: "Type",
        field: "route_type",
        width: 120,
        valueFormatter: (p) =>
          ROUTE_TYPE_LABELS[p.value as keyof typeof ROUTE_TYPE_LABELS] ?? p.value,
      },
      {
        headerName: "Status",
        field: "status",
        width: 120,
        cellRenderer: (params: ICellRendererParams<SynthesisRouteSummary>) => {
          const status = params.value as RouteStatus;
          return (
            <Badge variant={routeStatusVariant(status)}>
              {ROUTE_STATUS_LABELS[status] ?? status}
            </Badge>
          );
        },
      },
      {
        headerName: "Steps",
        field: "total_steps",
        width: 80,
        type: "numericColumn",
      },
      {
        headerName: "Yield (%)",
        field: "overall_yield",
        width: 100,
        type: "numericColumn",
        valueFormatter: (p) =>
          p.value != null ? `${(p.value as number).toFixed(1)}%` : "\u2014",
      },
      {
        headerName: "Scale",
        field: "scale",
        width: 110,
        valueFormatter: (p) =>
          p.value
            ? (ROUTE_SCALE_LABELS[p.value as keyof typeof ROUTE_SCALE_LABELS] ?? p.value)
            : "\u2014",
      },
      {
        headerName: "Source",
        field: "source",
        width: 110,
        valueFormatter: (p) =>
          (p.value as string)?.replace(/_/g, " ") ?? "\u2014",
      },
    ],
    []
  );

  if (error) {
    return (
      <ErrorState message="Failed to load synthesis routes." details={error.message} />
    );
  }

  return (
    <>
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">
            Synthesis Routes
          </h2>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Registered synthetic pathways for this compound.
          </p>
        </div>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          New Route
        </Button>
      </div>

      <div className="mt-4">
        <DataGrid<SynthesisRouteSummary>
          rowData={routes}
          columnDefs={columnDefs}
          loading={isLoading}
          height="calc(100vh - 320px)"
          onRowClick={(route) => setSelectedRouteId(route.id)}
          emptyState={
            <EmptyState
              icon={GitBranch}
              title="No synthesis routes"
              description="Add the first synthetic pathway for this compound."
              action={{ label: "New Route", onClick: () => setCreateOpen(true), icon: Plus }}
            />
          }
        />
      </div>

      <CreateRouteDialog
        moleculeId={moleculeId}
        open={createOpen}
        onOpenChange={setCreateOpen}
      />

      {/* Slide-in detail panel */}
      {selectedRouteId && (
        <div className="fixed inset-0 z-40 flex">
          {/* Backdrop */}
          <div
            className="flex-1 bg-black/40"
            onClick={() => setSelectedRouteId(null)}
          />
          {/* Panel */}
          <div className="relative w-full max-w-2xl overflow-y-auto bg-background shadow-xl">
            <div className="p-6">
              <SynthesisRouteDetail
                routeId={selectedRouteId}
                onClose={() => setSelectedRouteId(null)}
              />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
