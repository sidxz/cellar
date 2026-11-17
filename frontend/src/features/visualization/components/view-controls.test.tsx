import { ApiError } from "@/shared/lib/api/custom-instance";
import { onMutationError } from "@/shared/providers/query-provider";
import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { MAX_VIEW_CONFIG_BYTES } from "../lib/config-schema";
import type { DerivedSpec } from "../lib/derived";
import type { Filter } from "../lib/filters";
import { toDatasetRequest, visualizeHref } from "../lib/source-url";
import { OpenViewContext } from "../store/open-view-context";
import { WorkbenchProvider, useWorkbench } from "../store/workbench-context";
import { makePanel } from "../store/workbench-store";
import type { Dataset, DatasetSource, Level, SavedView } from "../types";

const state = vi.hoisted(() => ({ canEdit: true, replace: vi.fn(), reload: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: state.replace }),
}));
vi.mock("@/shared/hooks/use-current-user", () => ({ useCanEdit: () => state.canEdit }));
vi.mock("@/features/research-organization/hooks/use-projects", () => ({
  useProjects: () => ({ data: [] }),
}));
vi.mock("@/shared/lib/toast", () => ({ showError: vi.fn(), showSuccess: vi.fn() }));
vi.mock("@/shared/lib/api/custom-instance", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/shared/lib/api/custom-instance")>()),
  customInstance: vi.fn(),
}));

import { customInstance } from "@/shared/lib/api/custom-instance";
import { showError } from "@/shared/lib/toast";
import { ViewControls } from "./view-controls";

const P1 = "99999999-9999-4999-8999-999999999999";
const source: DatasetSource = { kind: "protocol", protocolId: P1 };
const ds: Dataset = {
  revision: "r",
  level: "wells",
  row_count: 2,
  row_ids: ["w1", "w2"],
  columns: [
    { key: "well_order", label: "Well order", kind: "number", provenance: {} },
    { key: "plate", label: "Plate", kind: "category", provenance: {} },
  ],
  values: { well_order: [1, 2], plate: ["P1", "P2"] },
};
const panel = makePanel("histogram", { x: "well_order" });
const config = { config_version: 2, panels: [panel], filters: [], labels: {}, derived: [] };
const rg1: DerivedSpec = {
  id: "rg1",
  kind: "rgroups",
  coreSmiles: "c1ccccc1[*:1]",
  name: "Core A",
};

function savedView(over: Partial<SavedView> = {}): SavedView {
  return {
    id: "v1",
    name: "Plate drift",
    level: "wells",
    visibility: "private",
    created_by: "u1",
    can_edit: true,
    version: 1,
    dataset: toDatasetRequest(source, "wells"),
    config,
    unresolved: [],
    ...over,
  };
}

const plateFilter = (values: string[]): Filter => ({
  id: "f-plate",
  kind: "category",
  key: "plate",
  values,
  includeMissing: true,
});

/** Edits the store the way the rail and toolbar would. */
function Probe() {
  const upsertFilter = useWorkbench((s) => s.upsertFilter);
  const undo = useWorkbench((s) => s.undo);
  return (
    <>
      <button type="button" onClick={() => upsertFilter(plateFilter(["P1"]))}>
        change
      </button>
      <button type="button" onClick={undo}>
        undo
      </button>
    </>
  );
}

function show({
  view = savedView() as SavedView | null,
  level = "wells" as Level,
  at = source,
  filters = [] as Filter[],
  derived = [] as DerivedSpec[],
  savedDerived = [] as DerivedSpec[],
} = {}) {
  const client = new QueryClient({
    mutationCache: new MutationCache({ onError: onMutationError }),
  });
  const open = view && { view, config: { ...config, derived: savedDerived }, reload: state.reload };
  const panels = [panel];
  render(
    <QueryClientProvider client={client}>
      <OpenViewContext.Provider value={open}>
        <WorkbenchProvider
          initialPanels={panels}
          initialFilters={filters}
          saved={view ? { panels, filters } : undefined}
        >
          <ViewControls source={at} level={level} ds={ds} derived={derived} />
          <Probe />
        </WorkbenchProvider>
      </OpenViewContext.Provider>
    </QueryClientProvider>,
  );
}

const dot = () => screen.queryByRole("img", { name: "Unsaved changes" });
const saveBtn = () => screen.getByRole("button", { name: "Save" });
const openMenu = () =>
  fireEvent.keyDown(screen.getByRole("button", { name: "More view actions" }), { key: "Enter" });

beforeAll(() => {
  Element.prototype.scrollIntoView ??= vi.fn();
  Element.prototype.hasPointerCapture ??= vi.fn(() => false);
  Element.prototype.releasePointerCapture ??= vi.fn();
});

beforeEach(() => {
  state.canEdit = true;
  state.replace.mockReset();
  state.reload.mockReset();
  vi.mocked(customInstance).mockReset();
  vi.mocked(showError).mockReset();
});

describe("ViewControls", () => {
  it("lists the protocol's saved views under Views, the open one marked, for viewers too", async () => {
    state.canEdit = false;
    vi.mocked(customInstance).mockResolvedValue([
      savedView(),
      savedView({ id: "v2", name: "Potency" }),
    ]);
    show();
    fireEvent.keyDown(screen.getByRole("button", { name: "Views" }), { key: "Enter" });
    expect(await screen.findByRole("menuitem", { name: /Plate drift/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("menuitem", { name: /Potency/ })).not.toHaveAttribute("aria-current");
    expect(vi.mocked(customInstance)).toHaveBeenCalledWith({
      url: "/api/v1/saved-visualizations",
      method: "GET",
      params: { protocol_id: P1 },
    });
    expect(screen.getByRole("menuitem", { name: "All saved views" })).toHaveAttribute(
      "href",
      "/assays/visualize",
    );
  });

  it("without a view, offers Save view…", () => {
    show({ view: null });
    expect(screen.getByRole("button", { name: "Save view…" })).toBeEnabled();
    expect(dot()).toBeNull();
  });

  it("shows the view's name, and the dot only while there are unsaved changes", () => {
    show();
    expect(screen.getByText("Plate drift")).toBeInTheDocument();
    expect(dot()).toBeNull();
    expect(saveBtn()).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "change" }));
    expect(dot()).not.toBeNull();
    expect(saveBtn()).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "undo" }));
    expect(dot()).toBeNull();
  });

  it("counts another level or source than the saved one as unsaved", () => {
    show({ level: "runs" });
    expect(dot()).not.toBeNull();
  });

  it("counts added or removed chemistry columns as unsaved", () => {
    show({ derived: [rg1] });
    expect(dot()).not.toBeNull();
  });

  it("reads the saved chemistry columns as saved", () => {
    show({ derived: [{ ...rg1 }], savedDerived: [rg1] });
    expect(dot()).toBeNull();
  });

  it("counts a change of runs as unsaved", () => {
    show({ at: { ...source, runIds: ["r1"] } });
    expect(dot()).not.toBeNull();
  });

  it("Save sends the version it was opened at, then reads as saved", async () => {
    vi.mocked(customInstance).mockResolvedValueOnce(savedView({ version: 2 }));
    show({ derived: [rg1], savedDerived: [rg1] });
    fireEvent.click(screen.getByRole("button", { name: "change" }));
    fireEvent.click(saveBtn());

    await waitFor(() => expect(dot()).toBeNull());
    expect(vi.mocked(customInstance)).toHaveBeenCalledWith({
      url: "/api/v1/saved-visualizations/v1",
      method: "PATCH",
      data: {
        expected_version: 1,
        dataset: toDatasetRequest(source, "wells"),
        config: {
          config_version: 2,
          panels: [panel],
          filters: [plateFilter(["P1"])],
          labels: { well_order: "Well order", plate: "Plate" },
          derived: [rg1],
        },
      },
    });
  });

  it("owner's menu: save as new, edit name and sharing, delete", () => {
    show();
    openMenu();
    expect(screen.getByRole("menuitem", { name: "Save as new view…" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Edit name and sharing…" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Delete view…" })).toBeInTheDocument();
  });

  it("someone else's view can only be saved as a new view", () => {
    show({ view: savedView({ can_edit: false }) });
    expect(screen.getByRole("button", { name: "Save as new view…" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "More view actions" })).not.toBeInTheDocument();
    expect(screen.queryByText("Edit name and sharing…")).not.toBeInTheDocument();
    expect(screen.queryByText("Delete view…")).not.toBeInTheDocument();
  });

  it("a viewer sees the view's name and nothing to save", () => {
    state.canEdit = false;
    show();
    expect(screen.getByText("Plate drift")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Save|view actions/ })).toBeNull();
  });

  it("a viewer without a view sees nothing", () => {
    state.canEdit = false;
    show({ view: null });
    expect(screen.queryByRole("button", { name: /Save/ })).toBeNull();
  });

  it("a save someone beat explains itself, with no error toast", async () => {
    vi.mocked(customInstance).mockRejectedValueOnce(
      new ApiError("API error: 409 — changed", 409, { error: "StaleEditError", message: "x" }),
    );
    show();
    fireEvent.click(screen.getByRole("button", { name: "change" }));
    fireEvent.click(saveBtn());

    expect(await screen.findByText("This view changed since you opened it")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Someone saved a newer version. Reload it to see theirs — your unsaved changes are lost — or keep yours as a new view.",
      ),
    ).toBeInTheDocument();
    expect(showError).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Reload view" }));
    expect(state.reload).toHaveBeenCalled();
  });

  it("a save that lost a race to another explains itself the same way, with no error toast", async () => {
    vi.mocked(customInstance).mockRejectedValueOnce(
      new ApiError("API error: 409 — conflict", 409, {
        error: "ConcurrencyConflictError",
        message: "x",
        retry: true,
      }),
    );
    show();
    fireEvent.click(screen.getByRole("button", { name: "change" }));
    fireEvent.click(saveBtn());

    expect(await screen.findByText("This view changed since you opened it")).toBeInTheDocument();
    expect(showError).not.toHaveBeenCalled();
  });

  it("the stale dialog's Save as new view… opens the save dialog", async () => {
    vi.mocked(customInstance).mockRejectedValueOnce(
      new ApiError("API error: 409", 409, { error: "StaleEditError" }),
    );
    show();
    fireEvent.click(screen.getByRole("button", { name: "change" }));
    fireEvent.click(saveBtn());
    fireEvent.click(await screen.findByRole("button", { name: "Save as new view…" }));
    expect(await screen.findByRole("heading", { name: "Save as new view" })).toBeInTheDocument();
  });

  it("settings too large to save disable Save and say why", () => {
    const values = Array.from({ length: 5_000 }, (_, i) => `plate-${i}-${"x".repeat(10)}`);
    // Unsaved (another level), so only the size keeps Save off.
    show({ filters: [plateFilter(values)], level: "runs" });
    expect(JSON.stringify(values).length).toBeGreaterThan(MAX_VIEW_CONFIG_BYTES);
    expect(
      screen.getByTitle(
        /^These settings are too large to save \(\d+ KB of 64 KB\)\. Remove some category filter values\.$/,
      ),
    ).toBeInTheDocument();
    // Unavailable but reachable by keyboard, so the reason can be read.
    expect(saveBtn()).toHaveAttribute("aria-disabled", "true");
    expect(saveBtn()).toBeEnabled();
    expect(saveBtn()).toHaveAccessibleDescription(/^These settings are too large to save/);
    fireEvent.click(saveBtn());
    expect(vi.mocked(customInstance)).not.toHaveBeenCalled();
  });

  it("settings too large to save leave Save as new view… reachable, saying why", () => {
    const values = Array.from({ length: 5_000 }, (_, i) => `plate-${i}-${"x".repeat(10)}`);
    show({ view: null, filters: [plateFilter(values)] });
    const saveAs = screen.getByRole("button", { name: "Save view…" });
    expect(saveAs).toHaveAttribute("aria-disabled", "true");
    expect(saveAs).toBeEnabled();
    expect(saveAs).toHaveAccessibleDescription(/^These settings are too large to save/);
    fireEvent.click(saveAs);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("deletes after confirming, leaving the workbench open unsaved", async () => {
    vi.mocked(customInstance).mockResolvedValueOnce(undefined);
    show({ level: "runs" });
    openMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete view…" }));
    expect(
      screen.getByText(
        "Delete “Plate drift”? People it's shared with lose it too. The data isn't affected.",
      ),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Delete view" }));

    await waitFor(() =>
      expect(state.replace).toHaveBeenCalledWith(visualizeHref(source, "runs"), { scroll: false }),
    );
    expect(vi.mocked(customInstance)).toHaveBeenCalledWith({
      url: "/api/v1/saved-visualizations/v1",
      method: "DELETE",
    });
  });
});
