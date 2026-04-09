"use client";

import { useState } from "react";
import { Pencil, Plus, Upload } from "lucide-react";
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
import { useDoseResponseByRun } from "../hooks/use-dose-response";
import { type Run, type PlateFormat } from "../types";
import { AddDoseResponseDialog } from "./add-dose-response-dialog";
import { AddReadoutDataDialog } from "./add-readout-data-dialog";
import { BulkReadoutImportDialog } from "./bulk-readout-import-dialog";
import { DoseResponseChart } from "./dose-response-chart";
import { EditQcMetricsDialog } from "./edit-qc-metrics-dialog";
import { PlateHeatmap } from "./plate-heatmap";
import { ReadoutDataTable } from "./readout-data-table";

// ─── QC Metrics Panel (inline) ────────────────────────────────────────────────

interface QcMetricsPanelProps {
  qcMetrics: Record<string, unknown> | null;
}

function QcMetricsPanel({ qcMetrics }: QcMetricsPanelProps) {
  if (!qcMetrics || Object.keys(qcMetrics).length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        No QC metrics available.
      </p>
    );
  }

  const entries = Object.entries(qcMetrics);

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      {entries.map(([key, value]) => (
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
  );
}

// ─── Run Data Panel ───────────────────────────────────────────────────────────

interface RunDataPanelProps {
  run: Run;
}

export function RunDataPanel({ run }: RunDataPanelProps) {
  const { data: curves } = useDoseResponseByRun(run.id);

  const [addReadoutOpen, setAddReadoutOpen] = useState(false);
  const [bulkImportOpen, setBulkImportOpen] = useState(false);
  const [addDoseResponseOpen, setAddDoseResponseOpen] = useState(false);
  const [editQcOpen, setEditQcOpen] = useState(false);

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
            </div>
            <ReadoutDataTable runId={run.id} protocolId={run.protocol_id} />
          </div>
        </TabsContent>

        {/* Plate Map */}
        <TabsContent value="plate-map">
          <div className="mt-4">
            {run.plate_format ? (
              <PlateHeatmap format={run.plate_format as PlateFormat} />
            ) : (
              <p className="py-8 text-center text-sm text-muted-foreground">
                No plate format specified for this run.
              </p>
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
            <DoseResponseChart curves={curves ?? []} isInteractive={!run.is_locked} />
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
    </>
  );
}
