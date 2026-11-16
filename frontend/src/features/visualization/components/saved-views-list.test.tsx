import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SavedViewSummary } from "../types";

const state = vi.hoisted(() => ({
  query: {} as { data?: SavedViewSummary[]; isLoading: boolean; error: Error | null },
  useSavedViews: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/assays/visualize",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
vi.mock("../hooks/use-saved-views", () => ({
  useSavedViews: (protocolId?: string) => {
    state.useSavedViews(protocolId);
    return state.query;
  },
}));
vi.mock("@/features/research-organization/hooks/use-projects", () => ({
  useProjects: () => ({ data: [{ id: "proj-1", name: "NadD lead series" }] }),
}));
vi.mock("@/shared/hooks/use-workspace-members", () => ({
  useMemberNames: () => (id: string) => (id === "u1" ? "A. Chen" : ""),
}));

type Col = {
  headerName?: string;
  field?: keyof SavedViewSummary;
  valueGetter?: (p: { data: SavedViewSummary }) => unknown;
  valueFormatter?: (p: { value: unknown }) => string;
  cellRenderer?: (p: { data: SavedViewSummary; value: unknown }) => ReactNode;
};
// AG Grid needs a layout engine; this stub draws each cell the way the column says to.
vi.mock("@/shared/components/data-grid/data-grid", () => ({
  DataGrid: (props: {
    rowData?: SavedViewSummary[];
    columnDefs: Col[];
    emptyState?: ReactNode;
    searchPlaceholder?: string;
  }) => {
    const cell = (c: Col, data: SavedViewSummary) => {
      const value = c.valueGetter ? c.valueGetter({ data }) : c.field && data[c.field];
      if (c.cellRenderer) return c.cellRenderer({ data, value });
      return c.valueFormatter ? c.valueFormatter({ value }) : String(value ?? "");
    };
    if (!props.rowData?.length) return <>{props.emptyState}</>;
    return (
      <table aria-label={props.searchPlaceholder}>
        <thead>
          <tr>
            {props.columnDefs.map((c) => (
              <th key={c.headerName}>{c.headerName}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {props.rowData.map((row) => (
            <tr key={row.id}>
              {props.columnDefs.map((c) => (
                <td key={c.headerName}>{cell(c, row)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    );
  },
}));

import { SavedViewsListPage } from "./saved-views-list";

const view = (over: Partial<SavedViewSummary>): SavedViewSummary => ({
  id: "v1",
  name: "View",
  level: "wells",
  visibility: "private",
  created_by: "u1",
  can_edit: true,
  version: 1,
  updated_at: new Date().toISOString(),
  ...over,
});

beforeEach(() => {
  state.useSavedViews.mockReset();
  state.query = { data: [], isLoading: false, error: null };
});

describe("SavedViewsListPage", () => {
  it("lists every view the chemist can see: name, level, owner, sharing and last update", () => {
    state.query.data = [
      view({ id: "v1", name: "Plate QC" }),
      view({
        id: "v2",
        name: "Potency",
        level: "compounds",
        visibility: "project",
        project_id: "proj-1",
      }),
    ];
    render(<SavedViewsListPage />);
    expect(state.useSavedViews).toHaveBeenCalledWith(undefined);
    expect(screen.getByRole("heading", { name: "Saved views" })).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Search by name…" });
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((h) => h.textContent),
    ).toEqual(["Name", "Level", "Owner", "Sharing", "Last updated"]);
    const [, qc, potency] = within(table).getAllByRole("row");
    expect(within(qc).getByRole("link", { name: "Plate QC" })).toHaveAttribute(
      "href",
      "/assays/visualize/v1",
    );
    expect(qc).toHaveTextContent(/Wells.*A\. Chen.*Private/);
    expect(within(potency).getByRole("link", { name: "Potency" })).toHaveAttribute(
      "href",
      "/assays/visualize/v2",
    );
    expect(potency).toHaveTextContent(/Compounds.*A\. Chen.*NadD lead series/);
  });

  it("with none saved, says how to save one", () => {
    render(<SavedViewsListPage />);
    expect(screen.getByText("No saved views yet")).toBeInTheDocument();
    expect(
      screen.getByText(/Open Visualize on a protocol or a run, set up the plots and filters/),
    ).toBeInTheDocument();
  });

  it("says when the list couldn't be loaded", () => {
    state.query = { isLoading: false, error: new Error("API error: 500") };
    render(<SavedViewsListPage />);
    expect(screen.getByText("Couldn't load the saved views")).toBeInTheDocument();
  });
});
