"use client";

import { useState } from "react";
import { Pencil, Plus, Upload } from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/shared/components/ui/tabs";
import { cn } from "@/shared/lib/utils";
import { useDoseResponseByRun } from "../hooks/use-dose-response";
import { usePlateMap } from "../hooks/use-plate-setup";
import { type Run, type PlateFormat } from "../types";
import { AddDoseResponseDialog } from "./add-dose-response-dialog";
import { AddReadoutDataDialog } from "./add-readout-data-dialog";
import { BulkReadoutImportDialog } from "./bulk-readout-import-dialog";
import { EditQcMetricsDialog } from "./edit-qc-metrics-dialog";
import { RunDoseResponseResults } from "./run-dr-results";
import { PlateHeatmap } from "./plate-heatmap";
import { PlateMapViewer } from "./plate-map-viewer";
import { PlateSetupDialog } from "./plate-setup-dialog";
import { ReadoutDataTable } from "./readout-data-table";
import { SimplifiedImportDialog } from "./simplified-import-dialog";

// ─── QC Metrics Panel (inline) ────────────────────────────────────────────────

interface QcMetricsPanelProps {
  qcMetrics: Record<string, unknown> | null;
}

/** Z' factor quality badge */
function ZPrimeBadge({ value }: { value: number }) {
  const { label, className } =
    value >= 0.5
      ? { label: "Excellent", className: "bg-green-500/20 text-green-400 border-green-500/30" }
      : value >= 0
      ? { label: "Marginal", className: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30" }
      : { label: "Poor", className: "bg-red-500/20 text-red-400 border-red-500/30" };

  return (
    <Badge variant="outline" className={cn("text-xs font-medium", className)}>
      {label}
    </Badge>
  );
}

function QcMetricsPanel({ qcMetrics }: QcMetricsPanelProps) {
  if (!qcMetrics || Object.keys(qcMetrics).length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        No QC metrics available.
      </p>
    );
  }

  // Detect Z' factor and control stats for special rendering
  const zPrime = typeof qcMetrics["z_prime"] === "number" ? (qcMetrics["z_prime"] as number) : null;
  const sbRatio = typeof qcMetrics["signal_to_background"] === "number"
    ? (qcMetrics["signal_to_background"] as number)
    : null;
  const posMean = typeof qcMetrics["positive_control_mean"] === "number"
    ? (qcMetrics["positive_control_mean"] as number)
    : null;
  const posSd = typeof qcMetrics["positive_control_sd"] === "number"
    ? (qcMetrics["positive_control_sd"] as number)
    : null;
  const negMean = typeof qcMetrics["negative_control_mean"] === "number"
    ? (qcMetrics["negative_control_mean"] as number)
    : null;
  const negSd = typeof qcMetrics["negative_control_sd"] === "number"
    ? (qcMetrics["negative_control_sd"] as number)
    : null;

  // Z' featured section
  const hasZPrime = zPrime !== null;

  // Remaining generic metrics (exclude fields already shown in featured section)
  const featuredKeys = new Set([
    "z_prime",
    "signal_to_background",
    "positive_control_mean",
    "positive_control_sd",
    "negative_control_mean",
    "negative_control_sd",
  ]);
  const genericEntries = Object.entries(qcMetrics).filter(
    ([key]) => !featuredKeys.has(key)
  );

  return (
    <div className="space-y-4">
      {/* Z' factor + control stats featured section */}
      {hasZPrime && (
        <div className="rounded-lg border bg-muted/20 p-4 space-y-3">
          <div className="flex items-center gap-3">
            <div>
              <p className="text-xs uppercase tracking-wide text-muted-foreground mb-1">
                Z&apos; Factor
              </p>
              <div className="flex items-center gap-2">
                <span className="text-2xl font-bold tabular-nums">
                  {zPrime!.toFixed(3)}
                </span>
                <ZPrimeBadge value={zPrime!} />
              </div>
            </div>
            {sbRatio !== null && (
              <div className="ml-6">
                <p className="text-xs uppercase tracking-wide text-muted-foreground mb-1">
                  S/B Ratio
                </p>
                <span className="text-2xl font-bold tabular-nums">
                  {sbRatio.toFixed(2)}
                </span>
              </div>
            )}
          </div>

          {(posMean !== null || negMean !== null) && (
            <div className="grid grid-cols-2 gap-3 pt-1 text-sm">
              {posMean !== null && (
                <div className="rounded-md bg-green-500/10 px-3 py-2">
                  <p className="text-xs text-muted-foreground mb-0.5">Pos Control</p>
                  <p className="font-medium tabular-nums">
                    {posMean.toFixed(3)}
                    {posSd !== null && (
                      <span className="text-xs text-muted-foreground ml-1">
                        ± {posSd.toFixed(3)}
                      </span>
                    )}
                  </p>
                </div>
              )}
              {negMean !== null && (
                <div className="rounded-md bg-red-500/10 px-3 py-2">
                  <p className="text-xs text-muted-foreground mb-0.5">Neg Control</p>
                  <p className="font-medium tabular-nums">
                    {negMean.toFixed(3)}
                    {negSd !== null && (
                      <span className="text-xs text-muted-foreground ml-1">
                        ± {negSd.toFixed(3)}
                      </span>
                    )}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Generic metrics grid */}
      {genericEntries.length > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {genericEntries.map(([key, value]) => (
            <Card key={key} className="py-4">
              <CardHeader className="pb-0">
                <CardTitle className="text-xs uppercase tracking-wide text-muted-foreground">
                  {key.replace(/_/g, " ")}
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-2">
                <p className="text-sm font-medium tabular-nums">
                  {typeof value === "number"
                    ? value.toFixed(3)
                    : String(value ?? "\u2014")}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Run Data Panel ───────────────────────────────────────────────────────────

interface RunDataPanelProps {
  run: Run;
}

export function RunDataPanel({ run }: RunDataPanelProps) {
  const { data: curves } = useDoseResponseByRun(run.id);
  const { data: plateMap } = usePlateMap(run.id);

  const [addReadoutOpen, setAddReadoutOpen] = useState(false);
  const [bulkImportOpen, setBulkImportOpen] = useState(false);
  const [importReadoutsOpen, setImportReadoutsOpen] = useState(false);
  const [addDoseResponseOpen, setAddDoseResponseOpen] = useState(false);
  const [editQcOpen, setEditQcOpen] = useState(false);
  const [plateSetupOpen, setPlateSetupOpen] = useState(false);

  const hasPlateMap = !!plateMap?.wells && plateMap.wells.length > 0;

  return (
    <>
      <Tabs defaultValue="readout">
        <TabsList>
          <TabsTrigger value="readout">Readout Data</TabsTrigger>
          <TabsTrigger value="plate-map">Plate Map</TabsTrigger>
          <TabsTrigger value="dose-response">Dose-Response</TabsTrigger>
          <TabsTrigger value="qc">QC Metrics</TabsTrigger>
        </TabsList>

        {/* Readout Data */}
        <TabsContent value="readout">
          <div className="mt-4">
            <div className="mb-4 flex gap-2">
              <Button
                size="sm"
                onClick={() => setAddReadoutOpen(true)}
                disabled={run.is_locked}
              >
                <Plus className="mr-2 h-4 w-4" /> Add Data
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setBulkImportOpen(true)}
                disabled={run.is_locked}
              >
                <Upload className="mr-2 h-4 w-4" /> Import CSV
              </Button>
              {hasPlateMap && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setImportReadoutsOpen(true)}
                  disabled={run.is_locked}
                >
                  <Upload className="mr-2 h-4 w-4" /> Import Readouts
                </Button>
              )}
            </div>
            <ReadoutDataTable runId={run.id} protocolId={run.protocol_id} />
          </div>
        </TabsContent>

        {/* Plate Map */}
        <TabsContent value="plate-map">
          <div className="mt-4">
            {hasPlateMap ? (
              <PlateMapViewer plateMap={plateMap} />
            ) : run.plate_format ? (
              <div className="space-y-4">
                <PlateHeatmap format={run.plate_format as PlateFormat} />
                {!run.is_locked && (
                  <div className="flex justify-center">
                    <Button
                      size="sm"
                      onClick={() => setPlateSetupOpen(true)}
                    >
                      <Plus className="mr-2 h-4 w-4" /> Set Up Plate
                    </Button>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center gap-4 py-12">
                <p className="text-sm text-muted-foreground">
                  No plate map has been configured for this run.
                </p>
                {!run.is_locked && (
                  <Button
                    size="sm"
                    onClick={() => setPlateSetupOpen(true)}
                  >
                    <Plus className="mr-2 h-4 w-4" /> Set Up Plate
                  </Button>
                )}
              </div>
            )}
          </div>
        </TabsContent>

        {/* Dose-Response */}
        <TabsContent value="dose-response">
          <div className="mt-4">
            <div className="mb-4">
              <Button
                size="sm"
                onClick={() => setAddDoseResponseOpen(true)}
                disabled={run.is_locked}
              >
                <Plus className="mr-2 h-4 w-4" /> Add Curve
              </Button>
            </div>
            <RunDoseResponseResults
              run={run}
              curves={curves ?? []}
              isLoading={!curves}
            />
          </div>
        </TabsContent>

        {/* QC Metrics */}
        <TabsContent value="qc">
          <div className="mt-4">
            <div className="mb-4">
              <Button
                size="sm"
                onClick={() => setEditQcOpen(true)}
                disabled={run.is_locked}
              >
                <Pencil className="mr-2 h-4 w-4" /> Edit Metrics
              </Button>
            </div>
            <QcMetricsPanel qcMetrics={run.qc_metrics} />
          </div>
        </TabsContent>
      </Tabs>

      {/* Dialogs */}
      <AddReadoutDataDialog
        runId={run.id}
        protocolId={run.protocol_id}
        open={addReadoutOpen}
        onOpenChange={setAddReadoutOpen}
      />
      <BulkReadoutImportDialog
        runId={run.id}
        open={bulkImportOpen}
        onOpenChange={setBulkImportOpen}
      />
      <SimplifiedImportDialog
        runId={run.id}
        open={importReadoutsOpen}
        onOpenChange={setImportReadoutsOpen}
      />
      <AddDoseResponseDialog
        runId={run.id}
        protocolId={run.protocol_id}
        open={addDoseResponseOpen}
        onOpenChange={setAddDoseResponseOpen}
      />
      <EditQcMetricsDialog
        run={run}
        open={editQcOpen}
        onOpenChange={setEditQcOpen}
      />
      <PlateSetupDialog
        runId={run.id}
        open={plateSetupOpen}
        onOpenChange={setPlateSetupOpen}
      />
    </>
  );
}
