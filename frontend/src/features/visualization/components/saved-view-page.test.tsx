import { TooltipProvider } from "@/shared/components/ui/tooltip";
import { ApiError } from "@/shared/lib/api/custom-instance";
import type { DecompositionAssignmentsResponse } from "@/shared/lib/api/model";
import { useBreadcrumbOverrides } from "@/shared/lib/stores/breadcrumb-store";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { ViewConfig } from "../lib/config-schema";
import { rgroupSet, withDerived } from "../lib/derived";
import { buildViewConfig } from "../lib/saved-view";
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
  decomposition: {} as Record<string, unknown>,
  assignments: {} as Record<string, unknown>,
  match: vi.fn(),
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
vi.mock("@/shared/components/chemistry", () => ({
  StructureThumbnail: () => null,
  StructureRenderer: () => null,
  StructureEditorDialog: () => null,
}));
vi.mock("@/features/sar-analysis/hooks/use-decomposition-run", () => ({
  useDecompositionRun: () => state.decomposition,
}));
vi.mock("../hooks/use-rgroup-assignments", () => ({
  useRGroupAssignments: (runId: string | null) =>
    runId ? state.assignments : { data: undefined, error: null },
}));
vi.mock("../hooks/use-substructure-match", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../hooks/use-substructure-match")>()),
  matchSubstructure: state.match,
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
      col("structure", "structure"),
      col("rd:s:raw", "number"),
    ],
    values: {
      compound: ["CEL-1", "CEL-2"],
      molecule_id: ["m1", "m2"],
      structure: ["Clc1ccccc1", "c1ccccc1"],
      "rd:s:raw": [1, 2],
    },
  };
}

const config = (over: Partial<ViewConfig> = {}): ViewConfig => ({
  config_version: 2,
  panels: [{ id: "saved-1", type: "histogram", x: "rd:s:raw", appearance: DEFAULT_APPEARANCE }],
  filters: [],
  labels: { "rd:s:raw": "Signal" },
  derived: [],
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
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  let level = levelOverride;
  const page = () => (
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <SavedViewPage viewId="v1" sourceOverride={sourceOverride} levelOverride={level} />
      </TooltipProvider>
    </QueryClientProvider>
  );
  const out = render(page());
  /** The page again, at ``next`` (the URL's level after a switch). */
  const rerender = (next: Level | null = level) => {
    level = next;
    out.rerender(page());
  };
  return { ...out, rerender };
}

const job = (over: Record<string, unknown> = {}) => ({
  runId: null,
  status: "running",
  counts: null,
  error: null,
  isCancelled: false,
  cancel: vi.fn(),
  ...over,
});

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
  state.decomposition = job();
  state.assignments = {
    data: {
      core_smiles: "c1ccccc1[*:1]",
      labels: ["R1"],
      assignments: { m1: { R1: "Cl[*:1]" }, m2: { R1: "[H][*:1]" } },
    },
    error: null,
  };
  state.match.mockReset();
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

  it("names the view in the breadcrumb, never by its id", () => {
    const { unmount } = show();
    const crumbs = renderHook(() => useBreadcrumbOverrides());
    expect(crumbs.result.current.get("v1")).toBe("Potency by compound");
    unmount();
    crumbs.rerender();
    expect(crumbs.result.current.has("v1")).toBe(false);
  });

  it("names a view it cannot load generically in the breadcrumb", () => {
    state.view = { data: undefined, isPending: true, isError: false };
    show();
    const crumbs = renderHook(() => useBreadcrumbOverrides());
    expect(crumbs.result.current.get("v1")).toBe("Saved view");
  });

  it("opens with the view's name and Save in the header", () => {
    show();
    expect(screen.getByText("Potency by compound")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("still reads an edit as unsaved after switching level and back", () => {
    const { rerender } = show();
    fireEvent.click(screen.getByRole("combobox", { name: /Add filter/ }));
    fireEvent.click(screen.getByRole("option", { name: "rd:s:raw" }));
    expect(screen.getByRole("img", { name: "Unsaved changes" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Runs" }));
    rerender("runs");
    fireEvent.click(screen.getByRole("button", { name: "Compounds" }));
    rerender("compounds");
    expect(screen.getByRole("group", { name: "rd:s:raw" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Unsaved changes" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
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
    state.view = loaded(savedView({ config: { ...config(), config_version: 3 } }));
    show();
    expect(
      screen.getByText(
        "This view was saved by a newer version of ChemCellar. Reload the page to open it.",
      ),
    ).toBeInTheDocument();
  });

  describe("with chemistry", () => {
    const POS = "chem:rg1:R1";
    const rg1 = {
      id: "rg1",
      kind: "rgroups",
      coreSmiles: "c1ccccc1[*:1]",
      name: "Core A",
    } as const;
    /** Saved from a workbench showing Core A's columns: a filter and a plot on R1. */
    const withRGroups = () => {
      const base = dataset("compounds");
      const assignments = state.assignments.data as DecompositionAssignmentsResponse;
      const shown = withDerived(base, [rgroupSet(rg1, base, assignments)]);
      const byR1 = { id: "saved-2", type: "bar" as const, category: POS, agg: "count" as const };
      const saved = buildViewConfig(
        {
          panels: [...config().panels, { ...byR1, appearance: DEFAULT_APPEARANCE }],
          filters: [
            { id: "f-r1", kind: "category", key: POS, values: ["Cl"], includeMissing: false },
          ],
        },
        shown,
        [rg1],
      );
      return loaded(savedView({ config: JSON.parse(JSON.stringify(saved)) }));
    };

    it("regenerates its R-group columns, then opens on the filter that uses them", () => {
      state.view = withRGroups();
      const { rerender } = show();
      expect(screen.getByText("Regenerating chemistry columns…")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Cancel R-groups · Core A" })).toBeInTheDocument();
      expect(document.querySelector('[data-panel-id="saved-1"]')).toBeNull();

      state.decomposition = job({
        runId: "run-1",
        status: "ready",
        counts: { matched: 2, unmatched: 0, total: 2 },
      });
      rerender();
      expect(screen.queryByText("Regenerating chemistry columns…")).not.toBeInTheDocument();
      expect(document.querySelector('[data-panel-id="saved-2"]')).not.toBeNull();
      expect(screen.getByText("1 / 2 compounds")).toBeInTheDocument();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      // Opened as saved: nothing to save.
      expect(screen.queryByRole("img", { name: "Unsaved changes" })).not.toBeInTheDocument();
    });

    it("lists a failed regeneration and drops the filter on its columns", () => {
      state.view = withRGroups();
      state.decomposition = job({ status: "failed", error: "The core is not a valid structure." });
      show();
      const banner = screen.getByRole("alert");
      expect(banner).toHaveTextContent(
        "R-groups · Core A couldn't be regenerated: The core is not a valid structure.",
      );
      expect(banner).toHaveTextContent("Not available any more: Filter: R1, Plot 2: Group (R1).");
      expect(screen.getByText("2 / 2 compounds")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    });

    const withQuery = () =>
      loaded(
        savedView({
          config: config({
            filters: [
              { id: "sub-1", kind: "substructure", query: "Clc1ccccc1", queryKind: "smiles" },
            ],
          }),
        }),
      );

    it("matches its substructure filter again before opening", async () => {
      state.view = withQuery();
      state.match.mockResolvedValue({ matched_ids: ["m1"], searched: 2, without_structure: 0 });
      show();
      expect(screen.getByText("Regenerating chemistry columns…")).toBeInTheDocument();
      expect(await screen.findByText("1 of 2 compounds match")).toBeInTheDocument();
      expect(screen.getByText("1 / 2 compounds")).toBeInTheDocument();
      expect(state.match).toHaveBeenCalledWith({
        query: "Clc1ccccc1",
        queryKind: "smiles",
        moleculeIds: ["m1", "m2"],
      });
      expect(screen.queryByRole("img", { name: "Unsaved changes" })).not.toBeInTheDocument();
    });

    it("keeps a substructure filter it couldn't match again, with Match again", async () => {
      const reason = "Cannot read “Clc1ccccc1” as a SMILES structure.";
      state.view = withQuery();
      state.match.mockRejectedValue(
        new ApiError(`API error: 422 — ${reason}`, 422, { message: reason }),
      );
      show();
      await waitFor(() =>
        expect(screen.getByRole("alert")).toHaveTextContent(
          `The filter “Contains Clc1ccccc1” couldn't be re-run: ${reason}`,
        ),
      );
      expect(
        screen.getByText("Not matched against this data yet — it filters nothing until matched."),
      ).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Match again" })).toBeInTheDocument();
    });
  });
});
