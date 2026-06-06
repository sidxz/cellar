"use client";

import { AttachmentList, FileUploadZone } from "@/features/attachment";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";
import { useHashTab } from "@/shared/hooks/use-hash-tab";
import { Grid3x3, Paperclip, Pencil, Upload } from "lucide-react";
import { useState } from "react";
import { useDoseResponseByRun } from "../hooks/use-dose-response";
import { usePlateMap } from "../hooks/use-plate-setup";
import { readPerPlateQc, worstZPrime } from "../lib/qc-metrics";
import type { PlateFormat, Run } from "../types";
import { EditQcMetricsDialog } from "./edit-qc-metrics-dialog";
import { GridImportDialog } from "./grid-import-dialog";
import { PlateHeatmap } from "./plate-heatmap";
import { PlateMapViewer } from "./plate-map-viewer";
import { ReadoutDataTable } from "./readout-data-table";
import { RunDoseResponseResults } from "./run-dr-results";
import { RunHeatmapPanel } from "./run-heatmap-panel";
import { RunImportWizard } from "./run-import-wizard";
import { SummaryImportWizard } from "./summary-import-wizard";
import { ZPrimeBadge } from "./z-prime-badge";

// ─── QC Metrics Panel (inline) ────────────────────────────────────────────────

interface QcMetricsPanelProps {
  qcMetrics: Record<string, unknown> | null;
}

function QcMetricsPanel({ qcMetrics }: QcMetricsPanelProps) {
  if (!qcMetrics || Object.keys(qcMetrics).length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">No QC metrics available.</p>
    );
  }

  const perPlate = readPerPlateQc(qcMetrics);
  const plateIds = Object.keys(perPlate);
  const worstZp = worstZPrime(qcMetrics);

  // Anything else on qc_metrics that isn't the per-plate z_prime block.
  const genericEntries = Object.entries(qcMetrics).filter(([k]) => k !== "z_prime");

  return (
    <div className="space-y-4">
      {worstZp !== null && (
        <div className="rounded-lg border bg-muted/20 p-4 space-y-3">
          <div className="flex items-center gap-3">
            <div>
              <p className="text-xs uppercase tracking-wide text-muted-foreground mb-1">
                Worst Z&apos; (across {plateIds.length} plate
                {plateIds.length === 1 ? "" : "s"})
              </p>
              <div className="flex items-center gap-2">
                <span className="text-2xl font-bold tabular-nums">{worstZp.toFixed(3)}</span>
                <ZPrimeBadge value={worstZp} />
              </div>
            </div>
          </div>
        </div>
      )}

      {plateIds.length > 0 && (
        <div className="rounded-md border">
          <table className="w-full text-sm">
            <thead className="bg-muted/30">
              <tr className="border-b text-xs text-muted-foreground">
                <th className="px-3 py-2 text-left font-medium">Plate</th>
                <th className="px-3 py-2 text-right font-medium">Z&apos;</th>
                <th className="px-3 py-2 text-right font-medium">S/B</th>
                <th className="px-3 py-2 text-right font-medium">POS mean ± SD</th>
                <th className="px-3 py-2 text-right font-medium">NEG mean ± SD</th>
                <th className="px-3 py-2 text-right font-medium">Classification</th>
              </tr>
            </thead>
            <tbody>
              {plateIds.map((pid, i) => {
                const q = perPlate[pid] || {};
                return (
                  <tr key={pid} className="border-b last:border-b-0">
                    <td className="px-3 py-2 text-xs text-muted-foreground">
                      {i + 1}
                      <span className="ml-2 font-mono text-[10px]">{pid.slice(0, 8)}…</span>
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {typeof q.z_prime === "number" ? q.z_prime.toFixed(3) : "—"}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {typeof q.s2b === "number" ? q.s2b.toFixed(2) : "—"}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {typeof q.pos_mean === "number"
                        ? `${q.pos_mean.toFixed(3)}${
                            typeof q.pos_sd === "number" ? ` ± ${q.pos_sd.toFixed(3)}` : ""
                          }`
                        : "—"}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {typeof q.neg_mean === "number"
                        ? `${q.neg_mean.toFixed(3)}${
                            typeof q.neg_sd === "number" ? ` ± ${q.neg_sd.toFixed(3)}` : ""
                          }`
                        : "—"}
                    </td>
                    <td className="px-3 py-2 text-right text-xs capitalize">
                      {q.classification ?? "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

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
                  {typeof value === "number" ? value.toFixed(3) : String(value ?? "\u2014")}
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

  const [editQcOpen, setEditQcOpen] = useState(false);
  const [runImportWizardOpen, setRunImportWizardOpen] = useState(false);
  const [summaryWizardOpen, setSummaryWizardOpen] = useState(false);
  const [gridImportOpen, setGridImportOpen] = useState(false);

  const plates = plateMap?.plates ?? [];
  const doseUnit = plateMap?.dose_unit ?? "uM";
  const hasPlateMap = plates.length > 0 && plates.some((p) => p.wells.length > 0);

  const [activeTab, setActiveTab] = useHashTab("readout");

  return (
    <>
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="readout">Readout Data</TabsTrigger>
          <TabsTrigger value="plate-map">Plate Map</TabsTrigger>
          <TabsTrigger value="heat-map">Heat Map</TabsTrigger>
          <TabsTrigger value="dose-response">Dose-Response</TabsTrigger>
          <TabsTrigger value="qc">QC Metrics</TabsTrigger>
          <TabsTrigger value="files">
            <Paperclip className="mr-1.5 size-4" />
            Files
          </TabsTrigger>
        </TabsList>

        {/* Readout Data */}
        <TabsContent value="readout">
          <div className="mt-3 space-y-3">
            <ReadoutDataTable
              runId={run.id}
              protocolId={run.protocol_id}
              toolbarActions={
                <>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button size="sm" disabled={run.is_locked}>
                        <Upload className="mr-2 h-4 w-4" /> Import
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onClick={() => setRunImportWizardOpen(true)}>
                        Import Run File (plate/well)
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => setSummaryWizardOpen(true)}>
                        Import Summary Results (compound + endpoints)
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setGridImportOpen(true)}
                    disabled={run.is_locked}
                  >
                    <Grid3x3 className="mr-2 h-4 w-4" /> Import Grid
                  </Button>
                </>
              }
            />
          </div>
        </TabsContent>

        {/* Plate Map — pure viewer. Ingest lives on the Readout Data tab. */}
        <TabsContent value="plate-map">
          <div className="mt-3 space-y-3">
            {hasPlateMap ? (
              plates.length > 1 ? (
                <Tabs defaultValue={plates[0].plate_id}>
                  <TabsList>
                    {plates.map((p) => (
                      <TabsTrigger key={p.plate_id} value={p.plate_id}>
                        Plate {p.plate_number}
                      </TabsTrigger>
                    ))}
                  </TabsList>
                  {plates.map((p) => (
                    <TabsContent key={p.plate_id} value={p.plate_id}>
                      <div className="mt-3">
                        <PlateMapViewer plate={p} doseUnit={doseUnit} />
                      </div>
                    </TabsContent>
                  ))}
                </Tabs>
              ) : (
                <PlateMapViewer plate={plates[0]} doseUnit={doseUnit} />
              )
            ) : run.plate_format ? (
              <div className="space-y-3">
                <PlateHeatmap format={run.plate_format as PlateFormat} />
                {!run.is_locked && (
                  <p className="text-center text-sm text-muted-foreground">
                    No data imported yet.{" "}
                    <button
                      type="button"
                      className="text-primary underline-offset-4 hover:underline"
                      onClick={() => setActiveTab("readout")}
                    >
                      Import on the Readout Data tab
                    </button>
                    .
                  </p>
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2 py-8">
                <p className="text-sm text-muted-foreground">
                  No plate map has been configured for this run.
                </p>
                {!run.is_locked && (
                  <p className="text-sm text-muted-foreground">
                    <button
                      type="button"
                      className="text-primary underline-offset-4 hover:underline"
                      onClick={() => setActiveTab("readout")}
                    >
                      Import on the Readout Data tab
                    </button>{" "}
                    to populate it.
                  </p>
                )}
              </div>
            )}
          </div>
        </TabsContent>

        {/* Heat Map */}
        <TabsContent value="heat-map">
          <RunHeatmapPanel run={run} />
        </TabsContent>

        {/* Dose-Response */}
        <TabsContent value="dose-response">
          <div className="mt-3 space-y-3">
            <RunDoseResponseResults run={run} curves={curves ?? []} isLoading={!curves} />
          </div>
        </TabsContent>

        {/* QC Metrics */}
        <TabsContent value="qc">
          <div className="mt-3 space-y-3">
            <div className="flex justify-end">
              <Button size="sm" onClick={() => setEditQcOpen(true)} disabled={run.is_locked}>
                <Pencil className="mr-2 h-4 w-4" /> Edit Metrics
              </Button>
            </div>
            <QcMetricsPanel qcMetrics={run.qc_metrics} />
          </div>
        </TabsContent>
        {/* Files */}
        <TabsContent value="files">
          <div className="mt-3 space-y-4">
            <FileUploadZone entityType="run" entityId={run.id} />
            <AttachmentList entityType="run" entityId={run.id} />
          </div>
        </TabsContent>
      </Tabs>

      {/* Dialogs */}
      <EditQcMetricsDialog run={run} open={editQcOpen} onOpenChange={setEditQcOpen} />
      <RunImportWizard
        runId={run.id}
        protocolId={run.protocol_id}
        open={runImportWizardOpen}
        onOpenChange={setRunImportWizardOpen}
      />
      <SummaryImportWizard
        runId={run.id}
        protocolId={run.protocol_id}
        open={summaryWizardOpen}
        onOpenChange={setSummaryWizardOpen}
      />
      <GridImportDialog
        runId={run.id}
        protocolId={run.protocol_id}
        open={gridImportOpen}
        onOpenChange={setGridImportOpen}
      />
    </>
  );
}
