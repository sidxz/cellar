import { ApiError } from "@/shared/lib/api/custom-instance";
import { onMutationError } from "@/shared/providers/query-provider";
import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { Filter } from "../lib/filters";
import { toDatasetRequest } from "../lib/source-url";
import { WorkbenchProvider } from "../store/workbench-context";
import { makePanel } from "../store/workbench-store";
import type { Dataset, DatasetSource, SavedView } from "../types";

const nav = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: nav.replace }) }));
vi.mock("@/features/research-organization/hooks/use-projects", () => ({
  useProjects: () => ({
    data: [
      { id: "proj-1", name: "NadD lead series", status: "active" },
      { id: "proj-2", name: "Closed one", status: "archived" },
    ],
  }),
}));
vi.mock("@/shared/lib/toast", () => ({
  showError: vi.fn(),
  showSuccess: vi.fn(),
}));
vi.mock("@/shared/lib/api/custom-instance", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/shared/lib/api/custom-instance")>()),
  customInstance: vi.fn(),
}));

import { customInstance } from "@/shared/lib/api/custom-instance";
import { showError } from "@/shared/lib/toast";
import { SaveViewDialog } from "./save-view-dialog";

const P1 = "99999999-9999-4999-8999-999999999999";
const ds: Dataset = {
  revision: "r",
  level: "wells",
  row_count: 2,
  row_ids: ["w1", "w2"],
  columns: [
    { key: "well_order", label: "Well order", kind: "number", provenance: {} },
    { key: "rd:X:raw", label: "Signal (AU)", kind: "number", provenance: {} },
  ],
  values: { well_order: [1, 2], "rd:X:raw": [3, 4] },
};
const panel = makePanel("scatter", { x: "well_order", y: "rd:X:raw" });
const range: Filter = {
  id: "f1",
  kind: "range",
  key: "rd:X:raw",
  min: 1,
  max: null,
  includeMissing: false,
};
const rows: Filter = { id: "selection", kind: "rows", rowIds: ["w1"] };
const allRuns: DatasetSource = { kind: "protocol", protocolId: P1 };

const view: SavedView = {
  id: "v1",
  name: "Plate drift",
  description: "Edge wells",
  level: "wells",
  visibility: "private",
  created_by: "u1",
  can_edit: true,
  version: 3,
  dataset: toDatasetRequest(allRuns, "wells"),
  config: { config_version: 2, panels: [], filters: [], labels: {}, derived: [] },
  unresolved: [],
};

function show(
  props: Partial<Parameters<typeof SaveViewDialog>[0]> = {},
  filters: Filter[] = [range, rows],
) {
  const client = new QueryClient({
    mutationCache: new MutationCache({ onError: onMutationError }),
  });
  const onOpenChange = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <WorkbenchProvider initialPanels={[panel]} initialFilters={filters}>
        <SaveViewDialog
          mode="create"
          source={allRuns}
          level="wells"
          ds={ds}
          derived={[]}
          open
          onOpenChange={onOpenChange}
          {...props}
        />
      </WorkbenchProvider>
    </QueryClientProvider>,
  );
  return { onOpenChange };
}

const name = () => screen.getByLabelText("Name");
const save = () => screen.getByRole("button", { name: "Save view" });

beforeAll(() => {
  Element.prototype.scrollIntoView ??= vi.fn();
  Element.prototype.hasPointerCapture ??= vi.fn(() => false);
  Element.prototype.releasePointerCapture ??= vi.fn();
});

beforeEach(() => {
  vi.mocked(customInstance).mockReset();
  vi.mocked(showError).mockReset();
  nav.replace.mockReset();
});

describe("SaveViewDialog", () => {
  it("needs a name, and a project when shared with one", () => {
    show();
    expect(save()).toBeDisabled();
    fireEvent.change(name(), { target: { value: "Plate drift" } });
    expect(save()).toBeEnabled();
    fireEvent.click(screen.getByRole("radio", { name: "Project — members of" }));
    expect(save()).toBeDisabled();
    fireEvent.click(screen.getByRole("radio", { name: "Private — only you" }));
    expect(save()).toBeEnabled();
  });

  it("says what a view saves, that the selection stays behind and later runs come in", () => {
    show();
    expect(
      screen.getByText(
        "Saves the plots, filters and level — never the data. Opening it loads current data.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Filter to selection isn't saved.")).toBeInTheDocument();
    expect(
      screen.getByText("Runs added to the protocol later will be included."),
    ).toBeInTheDocument();
  });

  it("leaves out the notes that don't apply", () => {
    show({ source: { kind: "protocol", protocolId: P1, runIds: ["r1"] } }, [range]);
    expect(screen.queryByText("Filter to selection isn't saved.")).not.toBeInTheDocument();
    expect(screen.queryByText(/Runs added to the protocol later/)).not.toBeInTheDocument();
  });

  it("creates the view from the source and plots, without the selection, and opens it", async () => {
    vi.mocked(customInstance).mockResolvedValueOnce({ ...view, id: "v-new" });
    const clusters = { id: "clusters", kind: "clusters", threshold: 0.4 } as const;
    show({ derived: [clusters] });
    expect(
      screen.getByText("Chemistry columns are computed again each time the view opens."),
    ).toBeInTheDocument();
    fireEvent.change(name(), { target: { value: "  Plate drift " } });
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Edge wells" } });
    fireEvent.click(save());

    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/assays/visualize/v-new"));
    expect(vi.mocked(customInstance)).toHaveBeenCalledWith({
      url: "/api/v1/saved-visualizations",
      method: "POST",
      data: {
        name: "Plate drift",
        description: "Edge wells",
        visibility: "private",
        project_id: null,
        dataset: toDatasetRequest(allRuns, "wells"),
        config: {
          config_version: 2,
          panels: [panel],
          filters: [range],
          labels: { well_order: "Well order", "rd:X:raw": "Signal (AU)" },
          derived: [clusters],
        },
      },
    });
  });

  it("shows the server's reason when it refuses, and stays open", async () => {
    const reason = "You need the editor role in this project to share with it.";
    vi.mocked(customInstance).mockRejectedValueOnce(
      new ApiError(`API error: 403 — ${reason}`, 403, { error: "ForbiddenError", message: reason }),
    );
    const { onOpenChange } = show();
    fireEvent.change(name(), { target: { value: "Plate drift" } });
    fireEvent.click(save());

    expect(await screen.findByText(reason)).toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
    expect(nav.replace).not.toHaveBeenCalled();
  });

  it("edits name, description and sharing only, from the version it was opened at", async () => {
    vi.mocked(customInstance).mockResolvedValueOnce({ ...view, version: 4, name: "Renamed" });
    const { onOpenChange } = show({ mode: "details", view });
    expect(name()).toHaveValue("Plate drift");
    expect(screen.queryByText(/never the data/)).not.toBeInTheDocument();
    fireEvent.change(name(), { target: { value: "Renamed" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(vi.mocked(customInstance)).toHaveBeenCalledWith({
      url: "/api/v1/saved-visualizations/v1",
      method: "PATCH",
      data: {
        expected_version: 3,
        name: "Renamed",
        description: "Edge wells",
        visibility: "private",
        project_id: null,
      },
    });
  });

  it("hands a stale edit to the caller instead of an error", async () => {
    vi.mocked(customInstance).mockRejectedValueOnce(
      new ApiError("API error: 409 — changed", 409, { error: "StaleEditError", message: "x" }),
    );
    const onStale = vi.fn();
    const { onOpenChange } = show({ mode: "details", view, onStale });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(onStale).toHaveBeenCalled());
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(showError).not.toHaveBeenCalled();
  });
});
