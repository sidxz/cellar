import type { SelectionChangedEvent } from "ag-grid-community";
import { useCallback, useMemo, useState } from "react";
import { useCompoundCurves, useMultiCompoundCurves } from "../../hooks/use-compound-curves";
import { useCompoundFlags, useCreateFlag, useDeleteFlag } from "../../hooks/use-compound-flags";
import { useProtocolActivity } from "../../hooks/use-protocol-activity";
import { interceptLabel } from "../../lib/intercept-label";
import type {
  CompoundActivity,
  CompoundFlag as CompoundFlagType,
  HitCriterion,
  Protocol,
} from "../../types";

// ---------------------------------------------------------------------------
// applyFilters — kept local; not exported. The component uses the filtered
// list from the hook, not the filter function directly.
// ---------------------------------------------------------------------------

const OPERATOR_LABELS: Record<string, string> = {
  gt: ">",
  lt: "<",
  gte: ">=",
  lte: "<=",
  in: "in",
};

function applyFilters(items: CompoundActivity[], criteria: HitCriterion[]): CompoundActivity[] {
  if (criteria.length === 0) return items;
  return items.filter((item) =>
    criteria.every((rule) => {
      if (rule.readout_name === "Curve Class") {
        if (rule.operator === "in" && Array.isArray(rule.value)) {
          return Object.values(item.readouts).some(
            (rv) => rv.curve_class != null && (rule.value as string[]).includes(rv.curve_class),
          );
        }
        return true;
      }
      const readout = item.readouts[rule.readout_name];
      if (!readout) return false;
      // Intercept-keyed criteria read from the curve's per-spec intercepts;
      // legacy (unkeyed) criteria stay on the headline best/primary value.
      let measured: number | null;
      if (rule.intercept_key) {
        const ivs = readout.curve_params?.intercept_values;
        const match = ivs?.find(
          (iv) =>
            iv.spec.kind === rule.intercept_key!.kind &&
            iv.spec.level === rule.intercept_key!.level,
        );
        measured = match?.value ?? null;
      } else {
        measured = readout.best;
      }
      if (measured == null) return false;
      const threshold = typeof rule.value === "number" ? rule.value : 0;
      switch (rule.operator) {
        case "gt":
          return measured > threshold;
        case "lt":
          return measured < threshold;
        case "gte":
          return measured >= threshold;
        case "lte":
          return measured <= threshold;
        default:
          return true;
      }
    }),
  );
}

export function criterionLabel(rule: HitCriterion): string {
  const op = OPERATOR_LABELS[rule.operator] ?? rule.operator;
  const val = Array.isArray(rule.value) ? rule.value.join(", ") : rule.value;
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

  // Hit criteria
  savedCriteria: HitCriterion[];
  activeCriteria: HitCriterion[];
  setActiveCriteria: React.Dispatch<React.SetStateAction<HitCriterion[]>>;
  isModified: boolean;

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
  const savedCriteria: HitCriterion[] = protocol.recommended_hit_criteria ?? [];
  const [activeCriteria, setActiveCriteria] = useState<HitCriterion[]>(savedCriteria);
  const isModified = JSON.stringify(activeCriteria) !== JSON.stringify(savedCriteria);

  // Sync savedCriteria when protocol updates (e.g. after dialog save)
  const prevSavedRef = JSON.stringify(protocol.recommended_hit_criteria ?? []);
  const [lastSynced, setLastSynced] = useState(prevSavedRef);
  if (prevSavedRef !== lastSynced) {
    setActiveCriteria(protocol.recommended_hit_criteria ?? []);
    setLastSynced(prevSavedRef);
  }

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

  const filteredItems = useMemo(() => {
    let items = applyFilters(activity?.items ?? [], activeCriteria);
    if (showFlaggedOnly) {
      items = items.filter((item) => flagsByMolecule.has(item.molecule_id));
    }
    return items;
  }, [activity?.items, activeCriteria, showFlaggedOnly, flagsByMolecule]);

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
    activeCriteria,
    setActiveCriteria,
    isModified,
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
