import type { z } from "zod";
import { createStore } from "zustand/vanilla";
import {
  MAX_PANELS,
  appearanceSchema,
  type overlaySchema,
  type panelSchema,
} from "../lib/config-schema";
import type { Filter } from "../lib/filters";

export { MAX_PANELS };
const MAX_HISTORY = 50;

export type PanelType = PanelConfig["type"];
export type Appearance = z.infer<typeof appearanceSchema>;
/** Display-only marks drawn over a plot; replaced wholesale through ``updatePanel``. */
export type OverlayConfig = z.infer<typeof overlaySchema>;
export type PanelConfig = z.infer<typeof panelSchema>;

export type PanelPatch = Partial<Omit<PanelConfig, "id" | "appearance">> & {
  appearance?: Partial<Appearance>;
};

export interface Snapshot {
  panels: PanelConfig[];
  filters: Filter[];
}

export interface WorkbenchState extends Snapshot {
  /** The panels and filters as last saved (by identity); null for a workbench with no saved view. */
  baseline: Snapshot | null;
  selection: ReadonlySet<string>;
  maximized: string | null;
  past: Snapshot[];
  future: Snapshot[];
  addPanel: (type: PanelType, defaults?: PanelPatch) => string | null;
  updatePanel: (id: string, patch: PanelPatch) => void;
  removePanel: (id: string) => void;
  setFilters: (filters: Filter[]) => void;
  upsertFilter: (filter: Filter) => void;
  removeFilter: (id: string) => void;
  /** Replace the panels and filters together, as one undo step. */
  setConfig: (panels: PanelConfig[], filters: Filter[]) => void;
  setSelection: (rowIds: Iterable<string>) => void;
  clearSelection: () => void;
  /** Turn the selection into a rows filter (one undo step) and clear it. */
  filterToSelection: () => void;
  setMaximized: (id: string | null) => void;
  undo: () => void;
  redo: () => void;
  /** ``saved`` (the panels and filters sent, by default the current ones) is now the view
   * as stored. */
  markSaved: (saved?: Snapshot) => void;
}

export const DEFAULT_APPEARANCE: Appearance = appearanceSchema.parse({});

export const canUndo = (s: WorkbenchState) => s.past.length > 0;
export const canRedo = (s: WorkbenchState) => s.future.length > 0;
/** Changed since the last save; undoing back to it restores the same arrays, so it reads clean. */
export const isDirty = (s: WorkbenchState) =>
  s.baseline !== null && (s.panels !== s.baseline.panels || s.filters !== s.baseline.filters);

let panelSeq = 0;

/** A panel of ``type`` with caller-computed ``defaults`` over the default appearance. */
export function makePanel(type: PanelType, defaults: PanelPatch = {}): PanelConfig {
  panelSeq += 1;
  const { appearance, ...rest } = defaults;
  return {
    id: `panel-${Date.now().toString(36)}-${panelSeq}`,
    type,
    ...rest,
    appearance: { ...DEFAULT_APPEARANCE, ...appearance },
  };
}

/** ``p`` with ``patch`` applied; appearance merges field by field. */
export function patchPanel(p: PanelConfig, patch: PanelPatch): PanelConfig {
  const { appearance, ...rest } = patch;
  return { ...p, ...rest, appearance: { ...p.appearance, ...appearance } };
}

/** A maximize survives history steps only while its panel exists. */
const keepMaximized = (id: string | null, panels: PanelConfig[]) =>
  id && panels.some((p) => p.id === id) ? id : null;

export function createWorkbenchStore(initial: {
  panels: PanelConfig[];
  filters?: Filter[];
  selection?: Iterable<string>;
  /** The view as last saved (a saved view's workbench): changes from it read as unsaved. */
  saved?: Snapshot;
  /** Told each snapshot ``markSaved`` takes, so it can outlive this store. */
  onSaved?: (saved: Snapshot) => void;
}) {
  const panels = initial.panels;
  const filters = initial.filters ?? [];
  return createStore<WorkbenchState>()((set, get) => {
    /** Apply a panels/filters change as one undoable step. */
    const commit = (next: Partial<Snapshot>) => {
      const { panels, filters, past } = get();
      set({
        ...next,
        past: [...past, { panels, filters }].slice(-MAX_HISTORY),
        future: [],
      });
    };

    return {
      panels,
      filters,
      baseline: initial.saved ?? null,
      selection: new Set<string>(initial.selection),
      maximized: null,
      past: [],
      future: [],

      addPanel: (type, defaults) => {
        if (get().panels.length >= MAX_PANELS) return null;
        const panel = makePanel(type, defaults);
        commit({ panels: [...get().panels, panel] });
        return panel.id;
      },
      updatePanel: (id, patch) => {
        commit({ panels: get().panels.map((p) => (p.id === id ? patchPanel(p, patch) : p)) });
      },
      removePanel: (id) => {
        commit({ panels: get().panels.filter((p) => p.id !== id) });
        if (get().maximized === id) set({ maximized: null });
      },
      setFilters: (filters) => commit({ filters }),
      upsertFilter: (filter) => {
        const filters = get().filters;
        const exists = filters.some((f) => f.id === filter.id);
        commit({
          filters: exists
            ? filters.map((f) => (f.id === filter.id ? filter : f))
            : [...filters, filter],
        });
      },
      removeFilter: (id) => commit({ filters: get().filters.filter((f) => f.id !== id) }),
      setConfig: (panels, filters) => commit({ panels, filters }),
      setSelection: (rowIds) => set({ selection: new Set(rowIds) }),
      clearSelection: () => set({ selection: new Set<string>() }),
      filterToSelection: () => {
        get().upsertFilter({ id: "selection", kind: "rows", rowIds: [...get().selection] });
        set({ selection: new Set<string>() });
      },
      setMaximized: (id) => set({ maximized: id }),
      undo: () => {
        const { past, future, panels, filters } = get();
        const prev = past.at(-1);
        if (!prev) return;
        set({
          ...prev,
          maximized: keepMaximized(get().maximized, prev.panels),
          past: past.slice(0, -1),
          future: [{ panels, filters }, ...future],
        });
      },
      redo: () => {
        const { past, future, panels, filters } = get();
        const next = future[0];
        if (!next) return;
        set({
          ...next,
          maximized: keepMaximized(get().maximized, next.panels),
          past: [...past, { panels, filters }],
          future: future.slice(1),
        });
      },
      markSaved: (saved) => {
        const baseline = saved ?? { panels: get().panels, filters: get().filters };
        set({ baseline });
        initial.onSaved?.(baseline);
      },
    };
  });
}

export type WorkbenchStore = ReturnType<typeof createWorkbenchStore>;
