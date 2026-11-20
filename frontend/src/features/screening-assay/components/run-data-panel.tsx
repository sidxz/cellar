"use client";

import { AttachmentList, FileUploadZone } from "@/features/attachment";
import { DetailTabsContent, DetailTabsList } from "@/shared/components/detail-tabs";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu";
import { Tabs, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";
import { useCanEdit } from "@/shared/hooks/use-current-user";
import { useHashTab } from "@/shared/hooks/use-hash-tab";
import { shortId } from "@/shared/lib/utils";
import {
  AlertTriangle,
  ChevronDown,
  FileSpreadsheet,
  Grid3x3,
  ListChecks,
  Microscope,
  Pencil,
  Upload,
} from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import { useDoseResponseByRun } from "../hooks/use-dose-response";
import { usePlateMap } from "../hooks/use-plate-setup";
import { useProtocol } from "../hooks/use-protocols";
import { instrumentFileRefusal } from "../lib/instrument-labelling";
import type { PlateColorBy } from "../lib/plate-map-values";
import { classifyZPrime, readPerPlateQc, worstZPrime } from "../lib/qc-metrics";
import type { Run } from "../types";
import { EditQcMetricsDialog } from "./edit-qc-metrics-dialog";
import { GridImportDialog } from "./grid-import-dialog";
import { InstrumentImportWizard } from "./instrument-import-wizard";
import { ReadoutDataTable } from "./readout-data-table";
import { RunCurvesPanel } from "./run-curves-panel";
import { RunDataSummary } from "./run-data-summary";
import { RunDetailsPanel } from "./run-details-panel";
import { RunDoseResponseResults } from "./run-dr-results";
import { RunImportWizard } from "./run-import-wizard";
import { RunPlatesPanel } from "./run-plates-panel";
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

  // Anything else on qc_metrics that isn't a per-plate block (z_prime here; plates in
  // the Data summary).
  const genericEntries = Object.entries(qcMetrics).filter(
    ([k]) => k !== "z_prime" && k !== "plates",
  );

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
                      <span className="ml-2 tabular-nums text-xs">{shortId(pid)}…</span>
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

/** The API's refusal for plate-shaped imports onto a run whose holder is not a plate. */
export const NOT_A_PLATE =
  "This run's holder is not a plate, so plate imports are not available for it.";
/** A disabled menu item ignores the pointer, which would hide its title; keep hover on. */
const HOVERABLE_WHEN_DISABLED = "data-[disabled]:pointer-events-auto";

interface RunDataPanelProps {
  run: Run;
  resultActions?: ReactNode;
}

function resultViewFromHash(hash: string): string | undefined {
  if (hash === "readout") return "readout";
  if (hash === "dose-response" || hash === "curves") return hash;
}

function plateViewFromHash(hash: string): PlateColorBy | undefined {
  if (hash === "plates" || hash === "heat-map") return "response";
  if (hash === "plate-map") return "compound";
  if (hash === "plate-concentration") return "concentration";
  if (hash === "plate-well-type") return "well-type";
}

function sectionFromHash(hash: string): string {
  if (plateViewFromHash(hash)) return "plates";
  if (hash === "quality" || hash === "qc") return "quality";
  if (hash === "details" || hash === "files") return hash;
  return "results";
}

export function RunDataPanel({ run, resultActions }: RunDataPanelProps) {
  const { data: curves, isLoading: curvesLoading } = useDoseResponseByRun(run.id);
  const { data: plateMap, isLoading: plateMapLoading } = usePlateMap(run.id);
  const { data: protocol, isLoading: protocolLoading } = useProtocol(run.protocol_id);
  const canEdit = useCanEdit();
  const [editQcOpen, setEditQcOpen] = useState(false);
  const [runImportWizardOpen, setRunImportWizardOpen] = useState(false);
  const [summaryWizardOpen, setSummaryWizardOpen] = useState(false);
  const [gridImportOpen, setGridImportOpen] = useState(false);
  const [instrumentWizardOpen, setInstrumentWizardOpen] = useState(false);

  const notPlate = plateMap?.plates.some((p) => p.holder_kind !== "plate") ?? false;
  const instrumentRefusal = instrumentFileRefusal(run);
  const hasCurves = !!plateMap?.has_measured_curves;
  const hasDoseResponse =
    !!curves?.length ||
    !!protocol?.readout_definitions.some(
      (d) => d.data_type === "dose_response" || d.dose_response_config,
    );
  const defaultResult = hasDoseResponse ? "dose-response" : hasCurves ? "curves" : "readout";

  // Keep existing readout/plate-map/heat-map/curves/qc links working.
  const [hashTab, setHashTab] = useHashTab("results");
  const [resultView, setResultView] = useState<string | null>(
    () => resultViewFromHash(hashTab) ?? null,
  );
  const [plateView, setPlateView] = useState<PlateColorBy>(
    () => plateViewFromHash(hashTab) ?? "response",
  );

  useEffect(() => {
    const result = resultViewFromHash(hashTab);
    const plate = plateViewFromHash(hashTab);
    if (result) setResultView(result);
    if (plate) setPlateView(plate);
  }, [hashTab]);

  const requestedSection = sectionFromHash(hashTab);
  const activeSection = notPlate && requestedSection === "plates" ? "results" : requestedSection;
  const requestedResult = resultViewFromHash(hashTab) ?? resultView ?? defaultResult;
  const resultsLoading =
    !resultViewFromHash(hashTab) &&
    resultView === null &&
    (curvesLoading || protocolLoading || plateMapLoading);
  const showTraces = hasCurves || (plateMapLoading && requestedResult === "curves");
  const activeResult =
    (requestedResult === "curves" && !showTraces) ||
    (requestedResult === "dose-response" && !hasDoseResponse)
      ? defaultResult
      : requestedResult;
  const activePlateView = plateViewFromHash(hashTab) ?? plateView;
  const zPrime = worstZPrime(run.qc_metrics);

  const openResultView = (view: string) => {
    setResultView(view);
    setHashTab(view === defaultResult ? "results" : view);
  };
  const openPlateView = (view: PlateColorBy) => {
    setPlateView(view);
    setHashTab(
      view === "compound"
        ? "plate-map"
        : view === "concentration"
          ? "plate-concentration"
          : view === "well-type"
            ? "plate-well-type"
            : "plates",
    );
  };
  const openSection = (section: string) => {
    if (section === "results" && resultsLoading) setHashTab("results");
    else if (section === "results") openResultView(activeResult);
    else if (section === "plates") openPlateView(activePlateView);
    else setHashTab(section);
  };

  const importMenu = canEdit && (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="sm" variant="outline" disabled={run.is_locked}>
          <Upload className="size-4" />
          Import
          <ChevronDown className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem
          disabled={notPlate}
          title={notPlate ? NOT_A_PLATE : undefined}
          className={HOVERABLE_WHEN_DISABLED}
          onClick={() => setRunImportWizardOpen(true)}
        >
          <FileSpreadsheet className="size-4" />
          Import Run File (plate/well)
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setSummaryWizardOpen(true)}>
          <ListChecks className="size-4" />
          Import Summary Results (compound + endpoints)
        </DropdownMenuItem>
        <DropdownMenuItem
          disabled={instrumentRefusal !== null}
          title={instrumentRefusal ?? undefined}
          className={HOVERABLE_WHEN_DISABLED}
          onClick={() => setInstrumentWizardOpen(true)}
        >
          <Microscope className="size-4" />
          Import Instrument File
        </DropdownMenuItem>
        <DropdownMenuItem
          disabled={notPlate}
          title={notPlate ? NOT_A_PLATE : undefined}
          className={HOVERABLE_WHEN_DISABLED}
          onClick={() => setGridImportOpen(true)}
        >
          <Grid3x3 className="size-4" />
          Import Grid
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );

  return (
    <>
      {zPrime !== null && classifyZPrime(zPrime) !== "excellent" && (
        <output className="flex flex-wrap items-center gap-2 rounded-md border border-amber-300/60 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>QC needs review. Worst plate Z′ is {zPrime.toFixed(2)}.</span>
          <button
            type="button"
            className="font-medium underline underline-offset-4"
            onClick={() => openSection("quality")}
          >
            Review quality
          </button>
        </output>
      )}
      <Tabs value={activeSection} onValueChange={openSection} className="gap-3">
        <DetailTabsList aria-label="Run sections">
          <TabsTrigger value="results">Results</TabsTrigger>
          {!notPlate && <TabsTrigger value="plates">Plates</TabsTrigger>}
          <TabsTrigger value="quality">Quality</TabsTrigger>
          <TabsTrigger value="details">Details</TabsTrigger>
          <TabsTrigger value="files">Files</TabsTrigger>
        </DetailTabsList>

        <DetailTabsContent value="results" activeValue={activeSection}>
          {resultsLoading ? (
            <p className="py-12 text-center text-sm text-muted-foreground">Loading results…</p>
          ) : (
            <Tabs value={activeResult} onValueChange={openResultView} className="gap-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <TabsList aria-label="Result view">
                  {hasDoseResponse && (
                    <TabsTrigger value="dose-response">Dose-response</TabsTrigger>
                  )}
                  {showTraces && <TabsTrigger value="curves">Traces</TabsTrigger>}
                  <TabsTrigger value="readout">Readouts</TabsTrigger>
                </TabsList>
                <div className="flex flex-wrap items-center gap-2">
                  {resultActions}
                  {importMenu}
                </div>
              </div>
              <DetailTabsContent value="readout" activeValue={activeResult}>
                <ReadoutDataTable runId={run.id} protocolId={run.protocol_id} />
              </DetailTabsContent>
              {hasDoseResponse && (
                <DetailTabsContent value="dose-response" activeValue={activeResult}>
                  <RunDoseResponseResults run={run} curves={curves ?? []} isLoading={!curves} />
                </DetailTabsContent>
              )}
              {showTraces && (
                <DetailTabsContent value="curves" activeValue={activeResult}>
                  {hasCurves ? (
                    <RunCurvesPanel runId={run.id} run={run} />
                  ) : (
                    <p className="py-12 text-center text-sm text-muted-foreground">
                      Loading traces…
                    </p>
                  )}
                </DetailTabsContent>
              )}
            </Tabs>
          )}
        </DetailTabsContent>

        {!notPlate && (
          <DetailTabsContent value="plates" activeValue={activeSection}>
            <RunPlatesPanel
              run={run}
              view={activePlateView}
              onViewChange={openPlateView}
              onOpenResults={() => openResultView("readout")}
            />
          </DetailTabsContent>
        )}

        <DetailTabsContent value="quality" activeValue={activeSection}>
          <div className="space-y-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold">Run quality</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Plate controls and assay quality compared with this protocol’s runs.
                </p>
              </div>
              {canEdit && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setEditQcOpen(true)}
                  disabled={run.is_locked}
                >
                  <Pencil className="size-4" /> Edit Metrics
                </Button>
              )}
            </div>
            <RunDataSummary run={run} protocol={protocol} />
            <QcMetricsPanel qcMetrics={run.qc_metrics ?? null} />
          </div>
        </DetailTabsContent>

        <DetailTabsContent value="details" activeValue={activeSection}>
          <RunDetailsPanel run={run} protocol={protocol} canEdit={canEdit} />
        </DetailTabsContent>

        <DetailTabsContent value="files" activeValue={activeSection}>
          <div className="space-y-4">
            {canEdit && <FileUploadZone entityType="run" entityId={run.id} />}
            <AttachmentList entityType="run" entityId={run.id} />
          </div>
        </DetailTabsContent>
      </Tabs>

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
      <InstrumentImportWizard
        runId={run.id}
        open={instrumentWizardOpen}
        onOpenChange={setInstrumentWizardOpen}
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
