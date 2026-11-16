import { describe, expect, it } from "vitest";
import type { Filter } from "../lib/filters";
import { MAX_PANELS, canRedo, canUndo, createWorkbenchStore } from "./workbench-store";

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
});
