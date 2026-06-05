"use client";

/**
 * AddFromRunsDialog (B6) — multi-run import with hit-criteria preview.
 *
 * 2-step flow:
 *   Step 1 "configure" — pick a protocol, multi-select runs, edit per-readout
 *                        channel configs (rule + hit threshold + use-for-filter),
 *                        global toggles (AND/OR, hits-only, default decision).
 *   Step 2 "preview"   — debounced preview (~300ms) renders a chip header +
 *                        molecule table with structure thumbnails + per-channel
 *                        cells. Commit posts /add-from-runs and closes.
 *
 * Backend invariants this dialog mirrors:
 *   - filter_mode default = "all"  (AND across active hit-criteria)
 *   - scope         default = "hits_only" (default_decision = SELECTED)
 *   - At least one run AND at least one channel_config required to enable Next.
 */

import { useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, Loader2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { MoleculeThumbnail } from "@/shared/components/molecule-thumbnail";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Checkbox } from "@/shared/components/ui/checkbox";
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
import { RadioGroup, RadioGroupItem } from "@/shared/components/ui/radio-group";
import { ScrollArea } from "@/shared/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Switch } from "@/shared/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/shared/components/ui/tooltip";
import { formatDate } from "@/shared/lib/format-date";
import { formatMeasurementValue } from "@/shared/lib/format-number";

import { useProtocol, useProtocolSummaries } from "@/features/screening-assay/hooks/use-protocols";
import type { ProtocolSummary } from "@/features/screening-assay/hooks/use-protocols";
import { channelUnit } from "@/features/screening-assay/lib/channel-unit";
import { deriveChannelHitDefaults } from "@/features/screening-assay/lib/hit-criteria-defaults";
import { interceptOptionLabel } from "@/features/screening-assay/lib/intercept-label";
import {
  type HitCriterion,
  type InterceptKey,
  type InterceptSpec,
  READOUT_NORMALIZATION_LABELS,
} from "@/features/screening-assay/types";
import {
  useAddResultsFromRunsApiV1CampaignsCampaignIdAddFromRunsPost,
  usePreviewRunImportApiV1CampaignsCampaignIdPreviewRunImportPost,
} from "@/shared/lib/api/campaigns/campaigns";
import { useListRunsByProtocolApiV1ProtocolsProtocolIdRunsGet } from "@/shared/lib/api/runs/runs";

import { campaignKeys } from "../hooks/use-campaigns";

// ── Local types ───────────────────────────────────────────────────────────────

interface ChannelConfigUI {
  protocol_id: string;
  readout_definition_id: string;
  label: string;
  source_kind: "readout_data" | "dose_response_curve";
  selection_rule: "latest_approved_run" | "mean_across_runs" | "geometric_mean";
  /** "lt" | "lte" | "gt" | "gte" | "between" | "" (no threshold) */
  hit_operator: string;
  /** For lt/gt/etc: a single number string. For "between": empty (use hit_value_low/high). */
  hit_value: string;
  /** For "between" operator only. */
  hit_value_low: string;
  hit_value_high: string;
  use_for_filter: boolean;
  /** Multi-select of curve classes ("full", "partial", "bell_shaped", "inactive").
   *  Empty array means "no class filter — all classes pass". DR-curve channels only. */
  allowed_curve_classes: string[];
  /** For readout_data channels with normalizations: picks which formula layer
   *  to read ("percent_inhibition" / "z_score" / …). null means the raw layer.
   *  Auto-derived from the readout's first non-`none` normalization on selection.
   *  Ignored for dose-response curve channels. */
  normalization_applied: string | null;
  /** Which dose-response intercept the threshold targets. `null` = primary
   *  (Surface #7 convention — also matches legacy channels saved before
   *  intercept_key existed). Carried forward verbatim from the protocol's
   *  recommended criterion via `deriveChannelHitDefaults`. Ignored for
   *  non-DR channels. */
  intercept_key: InterceptKey | null;
}

const ALL_CURVE_CLASSES = ["full", "partial", "bell_shaped", "inactive"] as const;

/**
 * Stable key for `userEditedConfigs`, disambiguating per intercept.
 *
 * Single-intercept readouts and non-DR channels keep `rd.id` as the key
 * (back-compat with pre-#13 saved-edit state and matches the natural
 * "one config per readout" mental model). Multi-intercept DR channels
 * past the primary get `${rd.id}:${kind}:${level}` so the chemist's edit
 * to the EC90 row doesn't clobber the EC50 row's saved state.
 *
 * The primary intercept on a multi-intercept readout still uses just
 * `rd.id` (its `intercept_key` is null per Surface #7's null-=-primary
 * convention) — that means primary edits on a multi-intercept readout
 * share the same key as the legacy single-channel-per-readout path.
 */
function channelConfigKey(readoutDefId: string, interceptKey: InterceptKey | null): string {
  if (interceptKey) return `${readoutDefId}:${interceptKey.kind}:${interceptKey.level}`;
  return readoutDefId;
}

interface AddFromRunsDialogProps {
  campaignId: string;
  projectId: string;
  open: boolean;
  onClose: () => void;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function AddFromRunsDialog({
  campaignId,
  projectId,
  open,
  onClose,
}: AddFromRunsDialogProps) {
  const qc = useQueryClient();
  const [step, setStep] = useState<"configure" | "preview">("configure");

  // — Step 1 state —
  const [protocolId, setProtocolId] = useState<string | null>(null);
  const [selectedRunIds, setSelectedRunIds] = useState<Set<string>>(new Set());
  // Only user-edited overrides live in state; the full channel config list is
  // derived below via useMemo so there is no effect feedback loop.
  const [userEditedConfigs, setUserEditedConfigs] = useState<Map<string, ChannelConfigUI>>(
    new Map(),
  );

  // — Global toggles —
  const [filterMode, setFilterMode] = useState<"any" | "all">("all");
  const [scope, setScope] = useState<"hits_only" | "all">("hits_only");
  const [defaultDecision, setDefaultDecision] = useState<"selected" | "deferred" | "rejected">(
    "selected",
  );
  const [refreshExisting, setRefreshExisting] = useState(false);
  const [approvedOnly, setApprovedOnly] = useState(true);

  // — Data —
  const { data: protocolsData } = useProtocolSummaries([projectId]);
  const protocols = protocolsData ?? [];
  // Hand-typed hook (returns the FE `Protocol` shape from screening-assay/types)
  // — necessary so `dose_response_config.intercepts` types as
  // `InterceptSpec[] | undefined` instead of orval's loose
  // `Record<string, unknown> | null`. The multi-intercept channel split
  // below needs to walk that list.
  const { data: protocolDetail } = useProtocol(protocolId ?? "", {
    enabled: !!protocolId,
  } as Parameters<typeof useProtocol>[1]);
  const { data: runs } = useListRunsByProtocolApiV1ProtocolsProtocolIdRunsGet(
    protocolId ?? "",
    undefined,
    { query: { enabled: !!protocolId } },
  );

  // Derive the full channel config list from protocol readouts, merging any
  // user edits stored in `userEditedConfigs`. Pure derivation — no effects or
  // feedback loops because user edits live in a separate map.
  //
  // Multi-intercept DR readouts (e.g. Resazurin with EC50 + EC90) expand into
  // one channel per declared intercept so the chemist sees both values + can
  // set independent hit thresholds. Single-intercept and non-DR readouts emit
  // one channel (the pre-#14 behavior).
  const channelConfigs = useMemo<ChannelConfigUI[]>(() => {
    if (!protocolDetail || selectedRunIds.size === 0) return [];
    const recommended = (protocolDetail.recommended_hit_criteria ??
      []) as unknown as HitCriterion[];

    // Build a single config — extracted so the multi-intercept path below
    // can call it once per intercept without duplicating the field-by-field
    // construction. `intercept` is null for non-DR readouts and for legacy
    // single-intercept DR readouts (treated identically since neither needs
    // an intercept-aware filter on the recommended criteria).
    const buildConfig = (
      rd: (typeof protocolDetail.readout_definitions)[number],
      intercept: InterceptSpec | null,
      isPrimary: boolean,
    ): ChannelConfigUI => {
      const isDoseResponse = rd.data_type === "dose_response";
      const primaryNorm = isDoseResponse
        ? null
        : (rd.normalizations?.find((n) => n !== "none") ?? null);
      const normSuffix = primaryNorm
        ? ` (${READOUT_NORMALIZATION_LABELS[primaryNorm as keyof typeof READOUT_NORMALIZATION_LABELS] ?? primaryNorm})`
        : "";
      // Wire convention (Surface #7): primary stores as `intercept_key=null`
      // so the binding tracks the protocol's current primary if intercepts
      // are reordered later. Non-primary stores explicit `{kind, level}`.
      const interceptKey: InterceptKey | null =
        !isPrimary && intercept ? { kind: intercept.kind, level: intercept.level } : null;

      // Filter mode: explicit `null`/`{kind,level}` only when we're in the
      // multi-intercept split (intercept != null). Single-intercept and
      // non-DR readouts pass `undefined` to keep the legacy "any criterion
      // on the readout" behavior — protocols predating Surface #7 didn't
      // mark their criteria with intercept_key, so filtering by null would
      // drop them incorrectly.
      const filterKey: InterceptKey | null | undefined = intercept ? interceptKey : undefined;

      const defaults = deriveChannelHitDefaults(
        recommended,
        { name: rd.name, data_type: rd.data_type },
        filterKey,
      );
      const hasThreshold = defaults.hit_operator !== "";

      // Channel label uses the shared dedupe-aware helper so a readout named
      // "EC50" with intercepts [EC50, EC90] reads as "EC50" / "EC90", not
      // "EC50 EC50" / "EC50 EC90". Non-DR / single-intercept paths keep
      // `rd.name` (with normalization suffix).
      const intercepts = rd.dose_response_config?.intercepts ?? [];
      const channelLabel = intercept
        ? interceptOptionLabel(rd.name, intercepts[0] ?? intercept, intercept)
        : `${rd.name}${normSuffix}`;

      return {
        protocol_id: protocolDetail.id,
        readout_definition_id: rd.id,
        label: channelLabel,
        source_kind: isDoseResponse ? "dose_response_curve" : "readout_data",
        selection_rule: "latest_approved_run" as const,
        hit_operator: defaults.hit_operator,
        hit_value: defaults.hit_value,
        hit_value_low: defaults.hit_value_low,
        hit_value_high: defaults.hit_value_high,
        use_for_filter: hasThreshold || isDoseResponse || defaults.allowed_curve_classes.length > 0,
        allowed_curve_classes: defaults.allowed_curve_classes,
        normalization_applied: primaryNorm,
        intercept_key: isDoseResponse ? interceptKey : null,
      };
    };

    return protocolDetail.readout_definitions
      .filter((rd) => rd.data_type !== "text") // text-only readouts aren't filterable
      .flatMap((rd) => {
        const intercepts = rd.dose_response_config?.intercepts ?? [];
        const isMultiIntercept = rd.data_type === "dose_response" && intercepts.length >= 2;

        const fresh: ChannelConfigUI[] = isMultiIntercept
          ? intercepts.map((spec, idx) => buildConfig(rd, spec, idx === 0))
          : [buildConfig(rd, null, true)];

        // Apply any per-config edits the chemist has made — keyed per
        // intercept so editing the EC90 row doesn't clobber the EC50 row.
        return fresh.map(
          (cfg) =>
            userEditedConfigs.get(channelConfigKey(cfg.readout_definition_id, cfg.intercept_key)) ??
            cfg,
        );
      });
  }, [protocolDetail, selectedRunIds.size, userEditedConfigs]);

  // — Mutations —
  const previewMutation = usePreviewRunImportApiV1CampaignsCampaignIdPreviewRunImportPost();
  const addMutation = useAddResultsFromRunsApiV1CampaignsCampaignIdAddFromRunsPost({
    mutation: {
      onSuccess: () => {
        void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) });
        handleClose();
      },
    },
  });

  // — Helpers —
  function buildPayload(): {
    run_ids: string[];
    channel_configs: {
      protocol_id: string;
      readout_definition_id: string;
      label: string;
      source_kind: string;
      selection_rule: string;
      hit_threshold: {
        readout_name: string;
        operator: string;
        value: number | number[];
        intercept_key: InterceptKey | null;
      } | null;
      use_for_filter: boolean;
      allowed_curve_classes?: string[] | null;
      normalization_applied?: string | null;
      // Channel-level intercept identity (Option A). Survives the wire
      // even when hit_threshold is null — keeps display-only EC90 channels
      // distinct from their primary-EC50 sibling on the same readout.
      intercept_key: InterceptKey | null;
    }[];
    filter_mode: "any" | "all";
  } {
    return {
      run_ids: [...selectedRunIds],
      channel_configs: channelConfigs.map((c) => {
        // intercept_key only meaningful on DR-curve channels (others read raw
        // values; no curve = no intercept). Mirrors channel-popover's save
        // logic so both creation paths stay coherent.
        const interceptKey =
          c.source_kind === "dose_response_curve" ? (c.intercept_key ?? null) : null;
        let hitThreshold: {
          readout_name: string;
          operator: string;
          value: number | number[];
          intercept_key: InterceptKey | null;
        } | null = null;
        if (c.hit_operator === "between") {
          const low = c.hit_value_low === "" ? null : Number(c.hit_value_low);
          const high = c.hit_value_high === "" ? null : Number(c.hit_value_high);
          if (
            low !== null &&
            !Number.isNaN(low) &&
            high !== null &&
            !Number.isNaN(high) &&
            low <= high
          ) {
            hitThreshold = {
              readout_name: c.label,
              operator: "between",
              value: [low, high],
              intercept_key: interceptKey,
            };
          }
        } else if (c.hit_operator) {
          const numericValue = c.hit_value === "" ? null : Number(c.hit_value);
          if (numericValue !== null && !Number.isNaN(numericValue)) {
            hitThreshold = {
              readout_name: c.label,
              operator: c.hit_operator,
              value: numericValue,
              intercept_key: interceptKey,
            };
          }
        }
        return {
          protocol_id: c.protocol_id,
          readout_definition_id: c.readout_definition_id,
          label: c.label,
          source_kind: c.source_kind,
          selection_rule: c.selection_rule,
          hit_threshold: hitThreshold,
          use_for_filter: c.use_for_filter,
          allowed_curve_classes:
            c.source_kind === "dose_response_curve" && c.allowed_curve_classes.length > 0
              ? c.allowed_curve_classes
              : null,
          normalization_applied: c.source_kind === "readout_data" ? c.normalization_applied : null,
          intercept_key: interceptKey,
        };
      }),
      filter_mode: filterMode,
    };
  }

  function handleClose() {
    setStep("configure");
    setProtocolId(null);
    setSelectedRunIds(new Set());
    setUserEditedConfigs(new Map());
    setFilterMode("all");
    setScope("hits_only");
    setDefaultDecision("selected");
    setRefreshExisting(false);
    setApprovedOnly(true);
    onClose();
  }

  const canGoToPreview = selectedRunIds.size > 0 && channelConfigs.length > 0;

  // — Debounced preview refresh —
  const [previewData, setPreviewData] = useState<{
    summary: {
      runs: number;
      channels_new: number;
      channels_reused: number;
      molecules_total: number;
      hits: number;
      non_hits: number;
      molecules_already_in_campaign: number;
    };
    rows: PreviewRow[];
    channels: { channel_key: string; label: string }[];
  } | null>(null);

  useEffect(() => {
    if (step !== "preview") return;
    const payload = buildPayload();
    if (payload.run_ids.length === 0 || payload.channel_configs.length === 0) return;
    const t = setTimeout(() => {
      previewMutation.mutate(
        { campaignId, data: payload },
        {
          onSuccess: (data) => setPreviewData(data as never),
        },
      );
    }, 300);
    return () => clearTimeout(t);
    // payload depends on the state below
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, channelConfigs, selectedRunIds, filterMode]);

  // — Render —
  const filteredRuns = (runs ?? []).filter((r) => (approvedOnly ? r.status === "approved" : true));

  return (
    <Dialog open={open} onOpenChange={(o) => !o && handleClose()}>
      <DialogContent className="sm:max-w-3xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-3">
            {step === "preview" && (
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => setStep("configure")}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
            )}
            Add compounds from protocol run(s)
          </DialogTitle>
          <DialogDescription>
            {step === "configure"
              ? "Pick runs and tune the hit criteria. Preview the would-be-added compounds before committing."
              : "Verify the compounds and cells that will be added. Go back to tweak criteria."}
          </DialogDescription>
        </DialogHeader>

        {step === "configure" ? (
          <ConfigureStep
            protocols={protocols}
            protocolId={protocolId}
            onProtocolChange={(id) => {
              setProtocolId(id);
              setSelectedRunIds(new Set());
              setUserEditedConfigs(new Map());
            }}
            runs={filteredRuns}
            selectedRunIds={selectedRunIds}
            onToggleRun={(id) => {
              setSelectedRunIds((prev) => {
                const next = new Set(prev);
                next.has(id) ? next.delete(id) : next.add(id);
                return next;
              });
            }}
            approvedOnly={approvedOnly}
            onApprovedOnlyChange={setApprovedOnly}
            channelConfigs={channelConfigs}
            protocolDetail={protocolDetail}
            onChannelConfigChange={(idx, patch) => {
              const cfg = channelConfigs[idx];
              if (!cfg) return;
              setUserEditedConfigs((prev) => {
                const next = new Map(prev);
                const updated = { ...cfg, ...patch };
                next.set(
                  channelConfigKey(updated.readout_definition_id, updated.intercept_key),
                  updated,
                );
                return next;
              });
            }}
            filterMode={filterMode}
            onFilterModeChange={setFilterMode}
            scope={scope}
            onScopeChange={setScope}
            defaultDecision={defaultDecision}
            onDefaultDecisionChange={setDefaultDecision}
            refreshExisting={refreshExisting}
            onRefreshExistingChange={setRefreshExisting}
          />
        ) : (
          <PreviewStep data={previewData} isLoading={previewMutation.isPending && !previewData} />
        )}

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={handleClose}>
            Cancel
          </Button>
          {step === "configure" ? (
            <Button onClick={() => setStep("preview")} disabled={!canGoToPreview}>
              Preview ({selectedRunIds.size} runs)
            </Button>
          ) : (
            <Button
              disabled={!previewData || addMutation.isPending}
              onClick={() => {
                const payload = buildPayload();
                addMutation.mutate({
                  campaignId,
                  data: {
                    ...payload,
                    scope,
                    default_decision: defaultDecision,
                    refresh_existing_cells: refreshExisting,
                  } as never,
                });
              }}
            >
              {addMutation.isPending
                ? "Adding…"
                : scope === "hits_only"
                  ? `Add ${previewData?.summary.hits ?? 0} hits`
                  : `Add ${previewData?.summary.molecules_total ?? 0} compounds`}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Step 1 — Configure ───────────────────────────────────────────────────────

interface RunSummary {
  id: string;
  run_date: string;
  status: string;
  molecule_count?: number | null;
  qc_metrics?: unknown;
}

interface ConfigureStepProps {
  protocols: ProtocolSummary[];
  protocolId: string | null;
  onProtocolChange: (id: string) => void;
  runs: RunSummary[];
  selectedRunIds: Set<string>;
  onToggleRun: (id: string) => void;
  approvedOnly: boolean;
  onApprovedOnlyChange: (v: boolean) => void;
  channelConfigs: ChannelConfigUI[];
  /** Full protocol with readout_definitions + dose_unit, threaded so the
   *  threshold input + caption can show the unit chemists expect. */
  protocolDetail?: {
    dose_unit?: string;
    readout_definitions: Array<{ id: string; name: string; unit?: string | null }>;
  };
  onChannelConfigChange: (idx: number, patch: Partial<ChannelConfigUI>) => void;
  filterMode: "any" | "all";
  onFilterModeChange: (v: "any" | "all") => void;
  scope: "hits_only" | "all";
  onScopeChange: (v: "hits_only" | "all") => void;
  defaultDecision: "selected" | "deferred" | "rejected";
  onDefaultDecisionChange: (v: "selected" | "deferred" | "rejected") => void;
  refreshExisting: boolean;
  onRefreshExistingChange: (v: boolean) => void;
}

function ConfigureStep(p: ConfigureStepProps) {
  return (
    <div className="space-y-4">
      {/* Protocol picker */}
      <div className="space-y-1">
        <Label>Protocol</Label>
        <Select value={p.protocolId ?? ""} onValueChange={p.onProtocolChange}>
          <SelectTrigger>
            <SelectValue placeholder="Choose protocol…" />
          </SelectTrigger>
          <SelectContent>
            {p.protocols.map((proto) => (
              <SelectItem key={proto.id} value={proto.id}>
                {proto.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {p.protocolId && (
        <>
          {/* Runs */}
          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <Label>Runs ({p.selectedRunIds.size} selected)</Label>
              <label className="flex items-center gap-2 text-xs">
                <Switch checked={p.approvedOnly} onCheckedChange={p.onApprovedOnlyChange} />
                Approved only
              </label>
            </div>
            <ScrollArea className="h-40 rounded border">
              {p.runs.length === 0 ? (
                <p className="p-3 text-xs text-muted-foreground">
                  No runs match the current filter.
                </p>
              ) : (
                <div className="divide-y text-xs">
                  {p.runs.map((r) => (
                    <label
                      key={r.id}
                      className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-muted/50"
                    >
                      <Checkbox
                        checked={p.selectedRunIds.has(r.id)}
                        onCheckedChange={() => p.onToggleRun(r.id)}
                      />
                      <span className="flex-1 min-w-0 truncate">
                        Run on {r.run_date ? formatDate(r.run_date) : "(unknown date)"}
                      </span>
                      <Badge
                        variant={r.status === "approved" ? "secondary" : "outline"}
                        className="text-[10px] px-1 py-0 shrink-0"
                      >
                        {r.status}
                      </Badge>
                      {r.molecule_count != null && (
                        <span className="text-muted-foreground text-[10px] shrink-0">
                          {r.molecule_count} mols
                        </span>
                      )}
                    </label>
                  ))}
                </div>
              )}
            </ScrollArea>
          </div>

          {/* Channel configs */}
          {p.channelConfigs.length > 0 && (
            <div className="space-y-2">
              <Label>Channels (one per readout)</Label>
              <div className="space-y-2">
                {p.channelConfigs.map((c, idx) => (
                  <div
                    key={channelConfigKey(c.readout_definition_id, c.intercept_key)}
                    className="rounded border p-3 space-y-2 bg-muted/20"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <Input
                        value={c.label}
                        onChange={(e) => p.onChannelConfigChange(idx, { label: e.target.value })}
                        className="h-7 text-sm font-medium"
                      />
                      <label className="flex items-center gap-1 text-xs text-muted-foreground shrink-0">
                        <Checkbox
                          checked={c.use_for_filter}
                          onCheckedChange={(v) =>
                            p.onChannelConfigChange(idx, {
                              use_for_filter: v === true,
                            })
                          }
                        />
                        Use for filter
                      </label>
                    </div>

                    <div className="grid grid-cols-1 gap-2">
                      <div>
                        <Label className="text-[10px] uppercase text-muted-foreground">
                          Selection rule
                        </Label>
                        <Select
                          value={c.selection_rule}
                          onValueChange={(v) =>
                            p.onChannelConfigChange(idx, {
                              selection_rule: v as ChannelConfigUI["selection_rule"],
                            })
                          }
                        >
                          <SelectTrigger className="h-7 text-xs">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="latest_approved_run">Latest approved run</SelectItem>
                            <SelectItem value="mean_across_runs">Mean across runs</SelectItem>
                            <SelectItem value="geometric_mean">Geometric mean</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      {(() => {
                        const rd = p.protocolDetail?.readout_definitions.find(
                          (r) => r.id === c.readout_definition_id,
                        );
                        const unit = channelUnit({
                          sourceKind: c.source_kind,
                          rawUnit: rd?.unit ?? null,
                          normalization: c.normalization_applied,
                          doseUnit: p.protocolDetail?.dose_unit ?? null,
                        });
                        const opLabel: Record<string, string> = {
                          lt: "<",
                          lte: "≤",
                          gt: ">",
                          gte: "≥",
                        };
                        const captionForValue = (val: string): string | null => {
                          const v = val.trim();
                          if (!v || Number.isNaN(Number(v))) return null;
                          const sym = opLabel[c.hit_operator] ?? c.hit_operator;
                          return `Hit if ${c.label} ${sym} ${v}${unit ? ` ${unit}` : ""}`;
                        };
                        const betweenCaption =
                          c.hit_operator === "between" &&
                          c.hit_value_low.trim() !== "" &&
                          c.hit_value_high.trim() !== "" &&
                          !Number.isNaN(Number(c.hit_value_low)) &&
                          !Number.isNaN(Number(c.hit_value_high))
                            ? `Hit if ${c.label} is between ${c.hit_value_low} and ${c.hit_value_high}${unit ? ` ${unit}` : ""}`
                            : null;
                        return (
                          <>
                            <div className="flex items-end gap-2 flex-wrap">
                              <div className="space-y-0.5">
                                <Label className="text-[10px] uppercase text-muted-foreground">
                                  Hit if
                                </Label>
                                <Select
                                  value={c.hit_operator}
                                  onValueChange={(v) =>
                                    p.onChannelConfigChange(idx, { hit_operator: v })
                                  }
                                >
                                  <SelectTrigger className="h-7 text-xs w-32">
                                    <SelectValue placeholder="(no threshold)" />
                                  </SelectTrigger>
                                  <SelectContent>
                                    <SelectItem value="lt">&lt; less than</SelectItem>
                                    <SelectItem value="lte">≤ at most</SelectItem>
                                    <SelectItem value="gt">&gt; greater than</SelectItem>
                                    <SelectItem value="gte">≥ at least</SelectItem>
                                    <SelectItem value="between">between (range)</SelectItem>
                                  </SelectContent>
                                </Select>
                              </div>

                              {c.hit_operator === "between" ? (
                                <div className="flex items-end gap-1 flex-1 min-w-0">
                                  <Input
                                    value={c.hit_value_low}
                                    onChange={(e) =>
                                      p.onChannelConfigChange(idx, {
                                        hit_value_low: e.target.value,
                                      })
                                    }
                                    placeholder="low"
                                    className="h-7 text-xs"
                                    type="number"
                                  />
                                  <span className="text-muted-foreground text-xs pb-1.5">and</span>
                                  <Input
                                    value={c.hit_value_high}
                                    onChange={(e) =>
                                      p.onChannelConfigChange(idx, {
                                        hit_value_high: e.target.value,
                                      })
                                    }
                                    placeholder="high"
                                    className="h-7 text-xs"
                                    type="number"
                                  />
                                  {unit && (
                                    <span className="text-muted-foreground text-xs pb-1.5">
                                      {unit}
                                    </span>
                                  )}
                                </div>
                              ) : c.hit_operator ? (
                                <div className="flex items-end gap-1 flex-1 min-w-0">
                                  <Input
                                    value={c.hit_value}
                                    onChange={(e) =>
                                      p.onChannelConfigChange(idx, {
                                        hit_value: e.target.value,
                                      })
                                    }
                                    placeholder="threshold"
                                    className="h-7 text-xs flex-1 min-w-0"
                                    type="number"
                                  />
                                  {unit && (
                                    <span className="text-muted-foreground text-xs pb-1.5">
                                      {unit}
                                    </span>
                                  )}
                                </div>
                              ) : null}
                            </div>
                            {(c.hit_operator === "between"
                              ? betweenCaption
                              : c.hit_operator
                                ? captionForValue(c.hit_value)
                                : null) && (
                              <p className="text-[10px] text-muted-foreground italic">
                                {c.hit_operator === "between"
                                  ? betweenCaption
                                  : captionForValue(c.hit_value)}
                              </p>
                            )}
                          </>
                        );
                      })()}

                      {/* Curve-class chip filter — DR-curve channels only */}
                      {c.source_kind === "dose_response_curve" && (
                        <div className="space-y-1">
                          <Label className="text-[10px] uppercase text-muted-foreground">
                            Curve class (leave empty for all)
                          </Label>
                          <div className="flex gap-1 flex-wrap">
                            {ALL_CURVE_CLASSES.map((cls) => {
                              const active = c.allowed_curve_classes.includes(cls);
                              return (
                                <button
                                  type="button"
                                  key={cls}
                                  onClick={() =>
                                    p.onChannelConfigChange(idx, {
                                      allowed_curve_classes: active
                                        ? c.allowed_curve_classes.filter((x) => x !== cls)
                                        : [...c.allowed_curve_classes, cls],
                                    })
                                  }
                                  className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors ${
                                    active
                                      ? "bg-primary text-primary-foreground border-primary"
                                      : "bg-background text-muted-foreground hover:bg-muted"
                                  }`}
                                >
                                  {cls.replace("_", " ")}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Global toggles */}
          <div className="rounded border p-3 space-y-3 bg-muted/10">
            <div className="space-y-1">
              <Label className="text-xs">Hit filter mode</Label>
              <Tabs
                value={p.filterMode}
                onValueChange={(v) => p.onFilterModeChange(v as "any" | "all")}
              >
                <TabsList className="h-7">
                  <TabsTrigger value="all" className="text-xs">
                    Hit per ALL criteria (strict)
                  </TabsTrigger>
                  <TabsTrigger value="any" className="text-xs">
                    Hit per ANY criterion (lenient)
                  </TabsTrigger>
                </TabsList>
              </Tabs>
            </div>

            <div className="space-y-1">
              <Label className="text-xs">What to add</Label>
              <RadioGroup
                value={p.scope}
                onValueChange={(v) => p.onScopeChange(v as "hits_only" | "all")}
                className="flex gap-4 text-xs"
              >
                <label className="flex items-center gap-1.5 cursor-pointer">
                  <RadioGroupItem value="hits_only" id="scope-hits" />
                  <span>Add only hits</span>
                </label>
                <label className="flex items-center gap-1.5 cursor-pointer">
                  <RadioGroupItem value="all" id="scope-all" />
                  <span>Add all compounds</span>
                </label>
              </RadioGroup>
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Default decision on new rows</Label>
              <RadioGroup
                value={p.defaultDecision}
                onValueChange={(v) =>
                  p.onDefaultDecisionChange(v as ConfigureStepProps["defaultDecision"])
                }
                className="flex gap-4 text-xs"
              >
                <label className="flex items-center gap-1.5 cursor-pointer">
                  <RadioGroupItem value="selected" id="dec-sel" />
                  <span>Selected</span>
                </label>
                <label className="flex items-center gap-1.5 cursor-pointer">
                  <RadioGroupItem value="deferred" id="dec-def" />
                  <span>Deferred</span>
                </label>
                <label className="flex items-center gap-1.5 cursor-pointer">
                  <RadioGroupItem value="rejected" id="dec-rej" />
                  <span>Rejected</span>
                </label>
              </RadioGroup>
            </div>

            <label className="flex items-center gap-2 text-xs cursor-pointer">
              <Switch checked={p.refreshExisting} onCheckedChange={p.onRefreshExistingChange} />
              Refresh non-override cells for molecules already in this campaign
            </label>
          </div>
        </>
      )}
    </div>
  );
}

// ── Step 2 — Preview ──────────────────────────────────────────────────────────

interface PreviewCell {
  channel_key: string;
  value: number | null;
  value_qualifier: string;
  unit: string;
  test_concentration_value: number | null;
  test_concentration_unit: string | null;
  replicate_count: number | null;
  qc_pass: boolean | null;
  /** Chemist-facing explanation for `qc_pass === false`. Backend formats
   *  ("Source run not approved" / "z' = 0.42 (below 0.5)" / aggregate). */
  qc_reason: string | null;
  hit_call: string | null;
}

interface PreviewRow {
  molecule: {
    id: string;
    registration_number: string | null;
    name: string | null;
    smiles: string | null;
  };
  is_hit: boolean;
  already_in_campaign: boolean;
  cells: PreviewCell[];
}

interface PreviewStepProps {
  data: {
    summary: {
      runs: number;
      channels_new: number;
      channels_reused: number;
      molecules_total: number;
      hits: number;
      non_hits: number;
      molecules_already_in_campaign: number;
    };
    rows: PreviewRow[];
    channels: { channel_key: string; label: string }[];
  } | null;
  isLoading: boolean;
}

function PreviewStep({ data, isLoading }: PreviewStepProps) {
  if (isLoading || !data) {
    return (
      <div className="flex items-center justify-center h-40">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }
  const { summary, channels } = data;
  // Hits first so the chemist sees the rows that matter without scanning;
  // already-in-campaign rows sink to the bottom (still dimmed). Stable
  // within each bucket so the molecule order from the backend response
  // (registration-number-ish) is preserved.
  const rows = [...data.rows].sort((a, b) => {
    if (a.already_in_campaign !== b.already_in_campaign) {
      return a.already_in_campaign ? 1 : -1;
    }
    if (a.is_hit !== b.is_hit) return a.is_hit ? -1 : 1;
    return 0;
  });

  return (
    <TooltipProvider delayDuration={120}>
      <div className="space-y-3">
        <div className="flex flex-wrap gap-2 text-xs">
          <Badge variant="secondary">{summary.molecules_total} molecules</Badge>
          <Badge className="bg-orange-100 text-orange-800 border border-orange-200">
            {summary.hits} hits
          </Badge>
          <Badge variant="outline">{summary.non_hits} non-hits</Badge>
          {summary.molecules_already_in_campaign > 0 && (
            <Badge variant="outline" className="text-muted-foreground">
              {summary.molecules_already_in_campaign} already in campaign
            </Badge>
          )}
          <Badge variant="outline">
            {summary.channels_new} new + {summary.channels_reused} reused channels
          </Badge>
        </div>

        <ScrollArea className="h-72 rounded border">
          <table className="w-full text-xs">
            <thead className="bg-muted/50 sticky top-0">
              <tr>
                <th className="text-left p-2">Compound</th>
                {channels.map((c) => (
                  <th key={c.channel_key} className="text-left p-2">
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y">
              {rows.map((r) => (
                <tr key={r.molecule.id} className={r.already_in_campaign ? "opacity-50" : ""}>
                  <td className="p-2 flex items-center gap-2">
                    <MoleculeThumbnail
                      smiles={r.molecule.smiles}
                      size="sm"
                      fallback={r.molecule.registration_number ?? r.molecule.name ?? "…"}
                    />
                    <div>
                      <div className="font-mono">
                        {r.molecule.registration_number ?? r.molecule.name ?? "—"}
                      </div>
                      {r.molecule.name && (
                        <div className="text-muted-foreground truncate max-w-[120px]">
                          {r.molecule.name}
                        </div>
                      )}
                      {r.already_in_campaign && (
                        <div className="text-[10px] text-muted-foreground italic">
                          already in campaign
                        </div>
                      )}
                    </div>
                  </td>
                  {channels.map((c) => {
                    const cell = r.cells.find((x) => x.channel_key === c.channel_key);
                    if (!cell || cell.value == null) {
                      return (
                        <td key={c.channel_key} className="p-2 text-muted-foreground">
                          —
                        </td>
                      );
                    }
                    return (
                      <td key={c.channel_key} className="p-2">
                        <div className="flex items-center gap-1">
                          <span>
                            {cell.value_qualifier !== "=" && cell.value_qualifier}
                            {formatMeasurementValue(cell.value)}{" "}
                            {cell.unit && cell.unit !== "-" ? cell.unit : ""}
                          </span>
                          {cell.hit_call === "hit" && (
                            <Badge className="bg-orange-100 text-orange-800 text-[9px] px-1 py-0">
                              HIT
                            </Badge>
                          )}
                          {cell.replicate_count != null && cell.replicate_count > 1 && (
                            <span className="text-[9px] text-muted-foreground">
                              N={cell.replicate_count}
                            </span>
                          )}
                          {cell.qc_pass === false && (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Badge className="bg-amber-100 text-amber-800 border border-amber-200 text-[9px] px-1 py-0 cursor-help">
                                  QC
                                </Badge>
                              </TooltipTrigger>
                              <TooltipContent>
                                {cell.qc_reason ?? "QC heuristic failed"}
                              </TooltipContent>
                            </Tooltip>
                          )}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollArea>
      </div>
    </TooltipProvider>
  );
}
