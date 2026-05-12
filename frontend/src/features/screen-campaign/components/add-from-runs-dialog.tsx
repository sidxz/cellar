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

import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, Loader2 } from "lucide-react";

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
import { MoleculeThumbnail } from "@/shared/components/molecule-thumbnail";
import { formatMeasurementValue } from "@/shared/lib/format-number";

import { useListProtocolsApiV1ProtocolsGet } from "@/shared/lib/api/protocols/protocols";
import { useGetProtocolApiV1ProtocolsProtocolIdGet } from "@/shared/lib/api/protocols/protocols";
import { useListRunsByProtocolApiV1ProtocolsProtocolIdRunsGet } from "@/shared/lib/api/runs/runs";
import {
  usePreviewRunImportApiV1CampaignsCampaignIdPreviewRunImportPost,
  useAddResultsFromRunsApiV1CampaignsCampaignIdAddFromRunsPost,
} from "@/shared/lib/api/campaigns/campaigns";

import { campaignKeys } from "../lib/hooks";

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
}

const ALL_CURVE_CLASSES = ["full", "partial", "bell_shaped", "inactive"] as const;

interface AddFromRunsDialogProps {
  campaignId: string;
  open: boolean;
  onClose: () => void;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function AddFromRunsDialog({ campaignId, open, onClose }: AddFromRunsDialogProps) {
  const qc = useQueryClient();
  const [step, setStep] = useState<"configure" | "preview">("configure");

  // — Step 1 state —
  const [protocolId, setProtocolId] = useState<string | null>(null);
  const [selectedRunIds, setSelectedRunIds] = useState<Set<string>>(new Set());
  const [channelConfigs, setChannelConfigs] = useState<ChannelConfigUI[]>([]);

  // — Global toggles —
  const [filterMode, setFilterMode] = useState<"any" | "all">("all");
  const [scope, setScope] = useState<"hits_only" | "all">("hits_only");
  const [defaultDecision, setDefaultDecision] = useState<
    "selected" | "deferred" | "rejected"
  >("selected");
  const [refreshExisting, setRefreshExisting] = useState(false);
  const [approvedOnly, setApprovedOnly] = useState(true);

  // — Data —
  const { data: protocolsResp } = useListProtocolsApiV1ProtocolsGet();
  const protocols = protocolsResp ?? [];
  const { data: protocolDetail } = useGetProtocolApiV1ProtocolsProtocolIdGet(
    protocolId ?? "",
    { query: { enabled: !!protocolId } },
  );
  const { data: runs } = useListRunsByProtocolApiV1ProtocolsProtocolIdRunsGet(
    protocolId ?? "",
    { query: { enabled: !!protocolId } },
  );

  // Auto-derive channel configs from selected runs + protocol readouts
  useEffect(() => {
    if (!protocolDetail || selectedRunIds.size === 0) {
      setChannelConfigs([]);
      return;
    }
    const existing = new Map(
      channelConfigs.map((c) => [c.readout_definition_id, c] as const),
    );
    const next: ChannelConfigUI[] = protocolDetail.readout_definitions
      .filter((rd) => rd.data_type !== "text")  // text-only readouts aren't filterable
      .map((rd) => {
        const prior = existing.get(rd.id);
        if (prior) return prior;
        const recommended = (protocolDetail.recommended_hit_criteria ?? []).find(
          (h) => h && (h as { readout_name?: string }).readout_name === rd.name,
        ) as { operator?: string; value?: number | string[] } | undefined;
        const hasNumericRecommended =
          recommended != null && typeof recommended.value === "number";
        // Auto-pick source kind: dose-response readouts come from the curves
        // table (fitted IC50/EC50/etc.), not the per-well ReadoutData.
        const isDoseResponse = rd.data_type === "dose_response";
        const result: ChannelConfigUI = {
          protocol_id: protocolDetail.id,
          readout_definition_id: rd.id,
          label: rd.name,
          source_kind: isDoseResponse ? "dose_response_curve" : "readout_data",
          selection_rule: "latest_approved_run",
          hit_operator: hasNumericRecommended ? (recommended!.operator ?? "lt") : "",
          hit_value: hasNumericRecommended ? String(recommended!.value) : "",
          hit_value_low: "",
          hit_value_high: "",
          // DR-curve readouts are the natural hit candidates → filter ON by default.
          use_for_filter: hasNumericRecommended || isDoseResponse,
          allowed_curve_classes: [],
        };
        return result;
      });
    setChannelConfigs(next);
  // We intentionally don't list channelConfigs in deps — it'd cause a feedback loop
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [protocolDetail?.id, selectedRunIds.size, protocolDetail?.readout_definitions.length]);

  // — Mutations —
  const previewMutation =
    usePreviewRunImportApiV1CampaignsCampaignIdPreviewRunImportPost();
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
      hit_threshold:
        | { readout_name: string; operator: string; value: number | number[] }
        | null;
      use_for_filter: boolean;
      allowed_curve_classes?: string[] | null;
    }[];
    filter_mode: "any" | "all";
  } {
    return {
      run_ids: [...selectedRunIds],
      channel_configs: channelConfigs.map((c) => {
        let hitThreshold:
          | { readout_name: string; operator: string; value: number | number[] }
          | null = null;
        if (c.hit_operator === "between") {
          const low = c.hit_value_low === "" ? null : Number(c.hit_value_low);
          const high = c.hit_value_high === "" ? null : Number(c.hit_value_high);
          if (
            low !== null && !Number.isNaN(low) &&
            high !== null && !Number.isNaN(high) &&
            low <= high
          ) {
            hitThreshold = {
              readout_name: c.label,
              operator: "between",
              value: [low, high],
            };
          }
        } else if (c.hit_operator) {
          const numericValue = c.hit_value === "" ? null : Number(c.hit_value);
          if (numericValue !== null && !Number.isNaN(numericValue)) {
            hitThreshold = {
              readout_name: c.label,
              operator: c.hit_operator,
              value: numericValue,
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
        };
      }),
      filter_mode: filterMode,
    };
  }

  function handleClose() {
    setStep("configure");
    setProtocolId(null);
    setSelectedRunIds(new Set());
    setChannelConfigs([]);
    setFilterMode("all");
    setScope("hits_only");
    setDefaultDecision("selected");
    setRefreshExisting(false);
    setApprovedOnly(true);
    onClose();
  }

  const canGoToPreview =
    selectedRunIds.size > 0 && channelConfigs.length > 0;

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
            onChannelConfigChange={(idx, patch) =>
              setChannelConfigs((prev) =>
                prev.map((c, i) => (i === idx ? { ...c, ...patch } : c)),
              )
            }
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
          <PreviewStep
            data={previewData}
            isLoading={previewMutation.isPending && !previewData}
          />
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

interface ProtocolSummary {
  id: string;
  name: string;
}

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
                <Switch
                  checked={p.approvedOnly}
                  onCheckedChange={p.onApprovedOnlyChange}
                />
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
                        Run on{" "}
                        {r.run_date
                          ? new Date(r.run_date).toLocaleDateString()
                          : "(unknown date)"}
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
                    key={c.readout_definition_id}
                    className="rounded border p-3 space-y-2 bg-muted/20"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <Input
                        value={c.label}
                        onChange={(e) =>
                          p.onChannelConfigChange(idx, { label: e.target.value })
                        }
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
                            <span className="text-muted-foreground text-xs pb-1.5">
                              and
                            </span>
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
                          </div>
                        ) : c.hit_operator ? (
                          <Input
                            value={c.hit_value}
                            onChange={(e) =>
                              p.onChannelConfigChange(idx, { hit_value: e.target.value })
                            }
                            placeholder="threshold"
                            className="h-7 text-xs flex-1 min-w-0"
                            type="number"
                          />
                        ) : null}
                      </div>

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
              <Tabs value={p.filterMode} onValueChange={(v) => p.onFilterModeChange(v as "any" | "all")}>
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
              <Switch
                checked={p.refreshExisting}
                onCheckedChange={p.onRefreshExistingChange}
              />
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
  const { summary, rows, channels } = data;

  return (
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
              <tr
                key={r.molecule.id}
                className={r.already_in_campaign ? "opacity-50" : ""}
              >
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
                          {formatMeasurementValue(cell.value)} {cell.unit && cell.unit !== "-" ? cell.unit : ""}
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
                          <Badge variant="destructive" className="text-[9px] px-1 py-0">
                            QC
                          </Badge>
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
  );
}
