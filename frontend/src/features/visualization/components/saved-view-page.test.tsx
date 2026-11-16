import { ApiError } from "@/shared/lib/api/custom-instance";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { ViewConfig } from "../lib/config-schema";
import { provenanceOf } from "../lib/traces/test-fixtures";
import { DEFAULT_APPEARANCE } from "../store/workbench-store";
import type { Dataset, DatasetColumn, DatasetSource, Level, SavedView } from "../types";

const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
const P1 = "99999999-9999-4999-8999-999999999999";
const R1 = "11111111-1111-4111-8111-111111111111";
const GONE = "rd:77777777-7777-4777-8777-777777777777:raw";

const state = vi.hoisted(() => ({
  view: {} as Record<string, unknown>,
  datasetCalls: [] as [unknown, unknown][],
  replace: vi.fn(),
  remove: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: state.replace }),
}));
vi.mock("@/shared/hooks/use-workspace-members", () => ({ useMemberNames: () => () => "" }));
vi.mock("@/features/screening-assay/hooks/use-runs", () => ({
  useRunsByProtocol: () => ({ data: [], isLoading: false }),
  useRun: () => ({ data: undefined }),
}));
vi.mock("@/features/screening-assay/hooks/use-protocols", () => ({
  useProtocol: () => ({ data: { id: P1, name: "NadD HTS" } }),
}));
vi.mock("@/shared/hooks/use-current-user", () => ({ useCanEdit: () => true }));
vi.mock("@/features/research-organization/hooks/use-collections", () => ({
  useCreateCollection: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("../hooks/use-run-row-counts", () => ({ useRunRowCounts: () => ({ data: undefined }) }));
vi.mock("../hooks/use-dataset", () => ({
  useDataset: (source: unknown, level: Level) => {
    state.datasetCalls.push([source, level]);
    return {
      data: source ? dataset(level) : undefined,
      isPending: !source,
      isError: false,
      refetch: vi.fn(),
    };
  },
}));
vi.mock("../hooks/use-saved-views", () => ({
  useSavedView: () => state.view,
  useUpdateSavedView: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteSavedView: () => ({ mutate: state.remove, isPending: false }),
}));

import { SavedViewPage } from "./saved-view-page";

const col = (key: string, kind: DatasetColumn["kind"], hidden = false): DatasetColumn => ({
  key,
  label: key,
  kind,
  provenance: provenanceOf(key),
  hidden,
});

/** Two compounds one row each, at whatever level was asked for. */
function dataset(level: Level): Dataset {
  return {
    revision: `rev-${level}`,
    level,
    row_count: 2,
    row_ids: ["m1", "m2"],
    columns: [
      col("compound", "category"),
      col("molecule_id", "text", true),
      col("rd:s:raw", "number"),
    ],
    values: { compound: ["CEL-1", "CEL-2"], molecule_id: ["m1", "m2"], "rd:s:raw": [1, 2] },
  };
}

const config = (over: Partial<ViewConfig> = {}): ViewConfig => ({
  config_version: 1,
  panels: [{ id: "saved-1", type: "histogram", x: "rd:s:raw", appearance: DEFAULT_APPEARANCE }],
  filters: [],
  labels: { "rd:s:raw": "Signal" },
  ...over,
});

function savedView(over: Partial<SavedView> = {}): SavedView {
  return {
    id: "v1",
    name: "Potency by compound",
    level: "compounds",
    visibility: "private",
    created_by: "u1",
    can_edit: true,
    version: 1,
    dataset: { level: "compounds", source: { kind: "protocol", protocol_id: P1, run_ids: [R1] } },
    config: config(),
    unresolved: [],
    ...over,
  };
}

const loaded = (view: SavedView) => ({ data: view, isPending: false, isError: false });

function show(sourceOverride: DatasetSource | null = null, levelOverride: Level | null = null) {
  return render(
    <SavedViewPage viewId="v1" sourceOverride={sourceOverride} levelOverride={levelOverride} />,
  );
}

beforeAll(() => {
  Element.prototype.scrollIntoView ??= vi.fn();
  Element.prototype.hasPointerCapture ??= vi.fn(() => false);
  Element.prototype.releasePointerCapture ??= vi.fn();
});

beforeEach(() => {
  state.datasetCalls = [];
  state.replace.mockReset();
  state.remove.mockReset();
  state.view = loaded(savedView());
});

describe("SavedViewPage", () => {
  it("opens the saved source at the saved level with the saved plots", () => {
    show();
    expect(state.datasetCalls.at(-1)).toEqual([
      { kind: "protocol", protocolId: P1, runIds: [R1] },
      "compounds",
    ]);
    expect(screen.getByRole("button", { name: "Compounds" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(document.querySelector('[data-panel-id="saved-1"]')).not.toBeNull();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("lets the URL's level and source override the saved ones", () => {
    show({ kind: "run", runId: R1 }, "runs");
    expect(state.datasetCalls.at(-1)).toEqual([{ kind: "run", runId: R1 }, "runs"]);
    expect(screen.getByRole("button", { name: "Runs" })).toHaveAttribute("aria-pressed", "true");
  });

  it("switches level within the view's own URL", () => {
    show();
    fireEvent.click(screen.getByRole("button", { name: "Runs" }));
    expect(state.replace).toHaveBeenCalledWith(
      `/assays/visualize/v1?protocol=${P1}&runs=${R1}&level=runs`,
      { scroll: false },
    );
  });

  it("lists what no longer resolves by label, never by id", () => {
    const lost = "1 of the 3 runs this view was saved with no longer exists; it was left out.";
    state.view = loaded(
      savedView({
        unresolved: [lost],
        config: config({
          filters: [
            { id: "f1", kind: "range", key: GONE, min: 1, max: null, includeMissing: false },
          ],
          labels: { "rd:s:raw": "Signal", [GONE]: "IC50 · NadD-counter" },
        }),
      }),
    );
    show();
    const banner = screen.getByRole("alert");
    expect(banner).toHaveTextContent(lost);
    expect(banner).toHaveTextContent("Not available any more: Filter: IC50 · NadD-counter.");
    expect(banner.textContent).not.toMatch(UUID);

    fireEvent.click(screen.getByRole("button", { name: "Dismiss view note" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("asks for no data when the saved protocol is gone", () => {
    const gone = "The protocol this view was built on no longer exists.";
    state.view = loaded(savedView({ dataset: null, unresolved: [gone] }));
    show();
    expect(screen.getByText(gone)).toBeInTheDocument();
    expect(state.datasetCalls.every(([source]) => source === null)).toBe(true);
  });

  it("lets the owner delete a view whose protocol is gone", () => {
    state.remove.mockImplementation((_id: string, opts: { onSuccess: () => void }) =>
      opts.onSuccess(),
    );
    state.view = loaded(savedView({ dataset: null, unresolved: ["Gone."] }));
    show();
    fireEvent.click(screen.getByRole("button", { name: "Delete view" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete view" }));
    expect(state.remove).toHaveBeenCalledWith("v1", expect.anything());
    expect(state.replace).toHaveBeenCalledWith("/assays");
  });

  it("offers no delete on a dead view someone else owns", () => {
    state.view = loaded(savedView({ dataset: null, unresolved: ["Gone."], can_edit: false }));
    show();
    expect(screen.queryByRole("button", { name: "Delete view" })).not.toBeInTheDocument();
  });

  it("opens with the view's name and Save in the header", () => {
    show();
    expect(screen.getByText("Potency by compound")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("says so when the view doesn't exist or isn't shared with the viewer", () => {
    state.view = {
      data: undefined,
      isPending: false,
      isError: true,
      error: new ApiError("API error: 404 — Not found", 404, { detail: "Not found" }),
    };
    show();
    expect(screen.getByText("This view doesn't exist or isn't shared with you.")).toBeVisible();
    expect(state.datasetCalls.every(([source]) => source === null)).toBe(true);
  });

  it("refuses a view saved by a newer version", () => {
    state.view = loaded(savedView({ config: { ...config(), config_version: 2 } }));
    show();
    expect(
      screen.getByText(
        "This view was saved by a newer version of ChemCellar. Reload the page to open it.",
      ),
    ).toBeInTheDocument();
  });
});
