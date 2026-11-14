import type { SelectionChangedEvent } from "ag-grid-community";
import { useCallback, useMemo, useState } from "react";
import { useCompoundCurves, useMultiCompoundCurves } from "../../hooks/use-compound-curves";
import { useCompoundFlags, useCreateFlag, useDeleteFlag } from "../../hooks/use-compound-flags";
import { useProtocolActivity } from "../../hooks/use-protocol-activity";
import { interceptLabel } from "../../lib/intercept-label";
import { meetsRule } from "../../lib/melt-hits";
import type {
  CompoundActivity,
  CompoundFlag as CompoundFlagType,
  HitCriterion,
  Protocol,
} from "../../types";

// ---------------------------------------------------------------------------
// Hit rule evaluation — the protocol's recommended rule applied per compound.
// ---------------------------------------------------------------------------

const OPERATOR_LABELS: Record<string, string> = {
  gt: ">",
  lt: "<",
  gte: ">=",
  lte: "<=",
  in: "in",
  not_between: "outside",
};

/** One rule against one compound: met, not met, or null when the compound has
 *  no value to test (missing readout, no curve class). The value is the
 *  compound's best across completed runs. */
export function ruleOutcome(item: CompoundActivity, rule: HitCriterion): boolean | null {
  if (rule.readout_name === "Curve Class") {
    const classes = Object.values(item.readouts)
      .map((rv) => rv.curve_class)
      .filter((c): c is NonNullable<typeof c> => c != null);
    if (classes.length === 0) return null;
    return (
      rule.operator === "in" &&
      Array.isArray(rule.value) &&
      classes.some((c) => (rule.value as string[]).includes(c))
    );
  }
  const readout = item.readouts[rule.readout_name];
  if (!readout) return null;
  // Intercept-keyed criteria read from the curve's per-spec intercepts;
  // legacy (unkeyed) criteria stay on the headline best/primary value.
  let measured: number | null;
  if (rule.intercept_key) {
    const ivs = readout.curve_params?.intercept_values;
    const match = ivs?.find(
      (iv) =>
        iv.spec.kind === rule.intercept_key?.kind && iv.spec.level === rule.intercept_key?.level,
    );
    measured = match?.value ?? null;
  } else {
    measured = readout.best;
  }
  if (measured == null) return null;
  return meetsRule(measured, rule);
}

export type HitStatus = "meets" | "fails" | "no_data";
export type StatusFilter = "all" | HitStatus;

/** The protocol's rule applied to a compound; null without a rule. A rule that
 *  fails decides; otherwise a rule with nothing to test leaves it undecided. */
export function hitStatus(item: CompoundActivity, criteria: HitCriterion[]): HitStatus | null {
  if (criteria.length === 0) return null;
  const outcomes = criteria.map((rule) => ruleOutcome(item, rule));
  if (outcomes.includes(false)) return "fails";
  return outcomes.includes(null) ? "no_data" : "meets";
}

export function criterionLabel(rule: HitCriterion): string {
  const op = OPERATOR_LABELS[rule.operator] ?? rule.operator;
  const val =
    rule.operator === "not_between" && Array.isArray(rule.value)
      ? rule.value.join(" – ")
      : Array.isArray(rule.value)
        ? rule.value.join(", ")
        : rule.value;
  if (rule.intercept_key) {
    // Surface the intercept (e.g. "Resazurin EC90 < 50"). Uses the implicit
    // KIND+LEVEL label since the protocol's `spec.label` isn't reachable
    // from a chip with only the rule in hand; if the protocol relabeled an
    // intercept ("Potency"), the chip still reads "EC90" — minor cosmetic
    // gap, acceptable since the dialog (which has the spec list) renders
    // the relabeled option name.
    const ik = interceptLabel({
      kind: rule.intercept_key.kind,
      level: rule.intercept_key.level,
      basis: "relative_percent",
      label: null,
    });
    return `${rule.readout_name} ${ik} ${op} ${val}`;
  }
  return `${rule.readout_name} ${op} ${val}`;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export interface UseActivityTabReturn {
  // Data
  activity: ReturnType<typeof useProtocolActivity>["data"];
  isLoading: boolean;
  readoutDefs: NonNullable<ReturnType<typeof useProtocolActivity>["data"]>["readout_definitions"];
  filteredItems: CompoundActivity[];

  // Flag state
  flags: CompoundFlagType[] | undefined;
  flagsByMolecule: Map<string, CompoundFlagType>;
  showFlaggedOnly: boolean;
  setShowFlaggedOnly: React.Dispatch<React.SetStateAction<boolean>>;
  handleToggleFlag: (moleculeId: string, existingFlagId: string | null) => void;

  // Hit criteria: the protocol's recommended rule, applied to every compound
  savedCriteria: HitCriterion[];
  /** Hit status per molecule; null when the protocol has no rule. */
  hits: Map<string, HitStatus> | null;
  statusCounts: Record<HitStatus, number>;
  statusFilter: StatusFilter;
  setStatusFilter: React.Dispatch<React.SetStateAction<StatusFilter>>;

  // Dialog state
  criteriaDialogOpen: boolean;
  setCriteriaDialogOpen: React.Dispatch<React.SetStateAction<boolean>>;
  collectionDialogOpen: boolean;
  setCollectionDialogOpen: React.Dispatch<React.SetStateAction<boolean>>;

  // Selection (checkbox-driven, multi-compound actions)
  selectedRows: CompoundActivity[];
  handleSelectionChanged: (event: SelectionChangedEvent<CompoundActivity>) => void;

  // Viewing (row-click-driven, single-compound detail sheet)
  viewingId: string | null;
  setViewingId: React.Dispatch<React.SetStateAction<string | null>>;
  viewing: CompoundActivity | null;
  selectedIndex: number;
  handlePrev: () => void;
  handleNext: () => void;

  // Single-compound curves (for detail sheet)
  compoundCurves: ReturnType<typeof useCompoundCurves>["data"];
  curvesLoading: boolean;

  // Multi-compound curves (2-5 selected, overlay comparison)
  multiMoleculeIds: string[];
  multiCurves: ReturnType<typeof useMultiCompoundCurves>["data"];
  multiCurvesLoading: boolean;
  hasDRCurves: boolean;
}

export function useActivityTab(protocol: Protocol, protocolId: string): UseActivityTabReturn {
  // ----- Data fetching -----
  const { data: activity, isLoading } = useProtocolActivity(protocolId);

  // ----- Flag state -----
  const { data: flags } = useCompoundFlags(protocolId);
  const createFlag = useCreateFlag(protocolId);
  const deleteFlag = useDeleteFlag(protocolId);
  const [showFlaggedOnly, setShowFlaggedOnly] = useState(false);

  const flagsByMolecule = useMemo(() => {
    const map = new Map<string, CompoundFlagType>();
    for (const f of flags ?? []) {
      if (f.flag_type === "star") map.set(f.molecule_id, f);
    }
    return map;
  }, [flags]);

  const handleToggleFlag = useCallback(
    (moleculeId: string, existingFlagId: string | null) => {
      if (existingFlagId) {
        deleteFlag.mutate(existingFlagId);
      } else {
        createFlag.mutate({ molecule_id: moleculeId });
      }
    },
    [createFlag, deleteFlag],
  );

  // ----- Hit criteria state -----
  const savedCriteria: HitCriterion[] = useMemo(
    () => protocol.recommended_hit_criteria ?? [],
    [protocol.recommended_hit_criteria],
  );
  // Every compound is listed; the status filter narrows by hit status.
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");

  // ----- Dialog state -----
  const [criteriaDialogOpen, setCriteriaDialogOpen] = useState(false);
  const [collectionDialogOpen, setCollectionDialogOpen] = useState(false);

  // ----- Selection state -----
  const [selectedRows, setSelectedRows] = useState<CompoundActivity[]>([]);
  const handleSelectionChanged = useCallback((event: SelectionChangedEvent<CompoundActivity>) => {
    setSelectedRows(event.api.getSelectedRows());
  }, []);

  // ----- Viewing state -----
  const [viewingId, setViewingId] = useState<string | null>(null);

  // ----- Derived data -----
  const readoutDefs = activity?.readout_definitions ?? [];

  const hits = useMemo(() => {
    if (savedCriteria.length === 0) return null;
    const map = new Map<string, HitStatus>();
    for (const item of activity?.items ?? []) {
      map.set(item.molecule_id, hitStatus(item, savedCriteria) as HitStatus);
    }
    return map;
  }, [activity?.items, savedCriteria]);

  const statusCounts = useMemo(() => {
    const counts: Record<HitStatus, number> = { meets: 0, fails: 0, no_data: 0 };
    for (const s of hits?.values() ?? []) counts[s] += 1;
    return counts;
  }, [hits]);

  const filteredItems = useMemo(() => {
    let items = activity?.items ?? [];
    if (hits && statusFilter !== "all") {
      items = items.filter((item) => hits.get(item.molecule_id) === statusFilter);
    }
    if (showFlaggedOnly) {
      items = items.filter((item) => flagsByMolecule.has(item.molecule_id));
    }
    return items;
  }, [activity?.items, hits, statusFilter, showFlaggedOnly, flagsByMolecule]);

  // ----- Navigation (prev/next of the currently viewed compound) -----
  const viewing = useMemo(
    () => filteredItems.find((r) => r.molecule_id === viewingId) ?? null,
    [filteredItems, viewingId],
  );
  const selectedIndex = viewing
    ? filteredItems.findIndex((r) => r.molecule_id === viewing.molecule_id)
    : -1;

  const navigateTo = useCallback(
    (index: number) => {
      const target = filteredItems[index];
      if (target) setViewingId(target.molecule_id);
    },
    [filteredItems],
  );

  const handlePrev = useCallback(() => {
    const newIdx = selectedIndex <= 0 ? filteredItems.length - 1 : selectedIndex - 1;
    navigateTo(newIdx);
  }, [selectedIndex, filteredItems.length, navigateTo]);

  const handleNext = useCallback(() => {
    const newIdx = selectedIndex >= filteredItems.length - 1 ? 0 : selectedIndex + 1;
    navigateTo(newIdx);
  }, [selectedIndex, filteredItems.length, navigateTo]);

  // ----- Single-compound detail curves -----
  const { data: compoundCurves, isLoading: curvesLoading } = useCompoundCurves(
    protocolId,
    viewing?.molecule_id ?? null,
  );

  // ----- Multi-compound overlay curves (2-5 selected) -----
  const multiMoleculeIds = useMemo(
    () =>
      selectedRows.length >= 2 && selectedRows.length <= 5
        ? selectedRows.map((r) => r.molecule_id)
        : [],
    [selectedRows],
  );

  const { data: multiCurves, isLoading: multiCurvesLoading } = useMultiCompoundCurves(
    protocolId,
    multiMoleculeIds,
  );

  const hasDRCurves = !!(multiCurves && multiCurves.length > 0);

  return {
    activity,
    isLoading,
    readoutDefs,
    filteredItems,
    flags,
    flagsByMolecule,
    showFlaggedOnly,
    setShowFlaggedOnly,
    handleToggleFlag,
    savedCriteria,
    hits,
    statusCounts,
    statusFilter,
    setStatusFilter,
    criteriaDialogOpen,
    setCriteriaDialogOpen,
    collectionDialogOpen,
    setCollectionDialogOpen,
    selectedRows,
    handleSelectionChanged,
    viewingId,
    setViewingId,
    viewing,
    selectedIndex,
    handlePrev,
    handleNext,
    compoundCurves,
    curvesLoading,
    multiMoleculeIds,
    multiCurves,
    multiCurvesLoading,
    hasDRCurves,
  };
}
