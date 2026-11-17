import { describe, expect, it, vi } from "vitest";
import type { Filter } from "../lib/filters";
import {
  MAX_PANELS,
  type PanelConfig,
  canRedo,
  canUndo,
  createWorkbenchStore,
  isDirty,
} from "./workbench-store";

const range = (id: string, min: number): Filter => ({
  id,
  kind: "range",
  key: "inh",
  min,
  max: null,
  includeMissing: false,
});

describe("workbench store", () => {
  it("refuses a fifth panel", () => {
    const store = createWorkbenchStore({ panels: [] });
    for (let i = 0; i < MAX_PANELS; i++)
      expect(store.getState().addPanel("scatter")).not.toBeNull();
    expect(store.getState().addPanel("histogram")).toBeNull();
    expect(store.getState().panels).toHaveLength(4);
  });

  it("undo restores the previous filters and redo re-applies them", () => {
    const store = createWorkbenchStore({ panels: [] });
    store.getState().upsertFilter(range("a", 10));
    store.getState().upsertFilter(range("a", 30));
    expect(store.getState().filters[0]).toMatchObject({ min: 30 });
    store.getState().undo();
    expect(store.getState().filters[0]).toMatchObject({ min: 10 });
    expect(canRedo(store.getState())).toBe(true);
    store.getState().redo();
    expect(store.getState().filters[0]).toMatchObject({ min: 30 });
  });

  it("a new change after undo drops the redo branch", () => {
    const store = createWorkbenchStore({ panels: [] });
    store.getState().upsertFilter(range("a", 10));
    store.getState().undo();
    store.getState().upsertFilter(range("b", 5));
    expect(canRedo(store.getState())).toBe(false);
  });

  it("setConfig swaps the panels and filters in one undo step and keeps the history", () => {
    const store = createWorkbenchStore({ panels: [] });
    store.getState().upsertFilter(range("a", 10));
    store.getState().addPanel("scatter", { x: "inh" });
    store.getState().setConfig([], [range("b", 5)]);
    expect(store.getState().panels).toEqual([]);
    expect(store.getState().filters.map((f) => f.id)).toEqual(["b"]);
    store.getState().undo();
    expect(store.getState().panels).toHaveLength(1);
    expect(store.getState().filters.map((f) => f.id)).toEqual(["a"]);
    store.getState().undo();
    store.getState().undo();
    expect(canUndo(store.getState())).toBe(false);
  });

  it("selection changes never create history entries", () => {
    const store = createWorkbenchStore({ panels: [] });
    store.getState().setSelection(["r1", "r2"]);
    store.getState().clearSelection();
    expect(canUndo(store.getState())).toBe(false);
  });

  it("changing filters keeps the selection", () => {
    const store = createWorkbenchStore({ panels: [] });
    store.getState().setSelection(["r1"]);
    store.getState().setFilters([range("a", 10)]);
    store.getState().removeFilter("a");
    expect([...store.getState().selection]).toEqual(["r1"]);
  });

  it("updatePanel merges appearance and is undoable", () => {
    const store = createWorkbenchStore({ panels: [] });
    const id = store.getState().addPanel("scatter", { x: "well_order", y: "inh" }) as string;
    store.getState().updatePanel(id, { appearance: { colorBy: "well_type" } });
    const panel = store.getState().panels[0];
    expect(panel).toMatchObject({ x: "well_order", y: "inh" });
    expect(panel.appearance).toMatchObject({
      colorBy: "well_type",
      opacity: 0.8,
      showFiltered: true,
    });
    store.getState().undo();
    expect(store.getState().panels[0].appearance.colorBy).toBeUndefined();
  });

  it("history is capped at 50 entries", () => {
    const store = createWorkbenchStore({ panels: [] });
    for (let i = 0; i < 60; i++) store.getState().upsertFilter(range("a", i));
    let undos = 0;
    while (canUndo(store.getState())) {
      store.getState().undo();
      undos += 1;
    }
    expect(undos).toBe(50);
  });

  it("removing the maximized panel clears maximize", () => {
    const store = createWorkbenchStore({ panels: [] });
    const id = store.getState().addPanel("box") as string;
    store.getState().setMaximized(id);
    store.getState().removePanel(id);
    expect(store.getState().maximized).toBeNull();
  });

  /** A saved view's store, opened on its saved panels and filters. */
  const savedStore = (onSaved?: (s: { panels: PanelConfig[]; filters: Filter[] }) => void) => {
    const panels: PanelConfig[] = [];
    const filters = [range("a", 1)];
    return createWorkbenchStore({ panels, filters, saved: { panels, filters }, onSaved });
  };

  it("a saved store is dirty only while it differs from its last save", () => {
    const store = savedStore();
    expect(isDirty(store.getState())).toBe(false);
    store.getState().upsertFilter(range("a", 10));
    expect(isDirty(store.getState())).toBe(true);
    store.getState().undo();
    expect(isDirty(store.getState())).toBe(false);
    store.getState().redo();
    store.getState().markSaved();
    expect(isDirty(store.getState())).toBe(false);
    store.getState().undo();
    expect(isDirty(store.getState())).toBe(true);
  });

  it("markSaved takes the panels and filters that were saved, not later edits, and says so", () => {
    const onSaved = vi.fn();
    const store = savedStore(onSaved);
    store.getState().upsertFilter(range("a", 10));
    const sent = { panels: store.getState().panels, filters: store.getState().filters };
    store.getState().upsertFilter(range("a", 20));
    store.getState().markSaved(sent);
    expect(onSaved).toHaveBeenCalledWith(sent);
    expect(isDirty(store.getState())).toBe(true);
    store.getState().undo();
    expect(isDirty(store.getState())).toBe(false);
  });

  it("an unsaved store is never dirty", () => {
    const store = createWorkbenchStore({ panels: [] });
    store.getState().upsertFilter(range("a", 10));
    store.getState().addPanel("scatter");
    expect(isDirty(store.getState())).toBe(false);
  });

  it("undo and redo drop a maximize whose panel no longer exists", () => {
    const store = createWorkbenchStore({ panels: [] });
    store.getState().addPanel("scatter");
    const b = store.getState().addPanel("box") as string;
    store.getState().setMaximized(b);
    store.getState().undo();
    expect(store.getState().maximized).toBeNull();
    store.getState().redo();
    store.getState().setMaximized(b);
    store.getState().removePanel(b);
    store.getState().undo();
    store.getState().setMaximized(b);
    store.getState().redo();
    expect(store.getState().maximized).toBeNull();
  });
});
