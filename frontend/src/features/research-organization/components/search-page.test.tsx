import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SearchQuery } from "../types";

const mocks = vi.hoisted(() => ({
  mutateAsync: vi.fn(),
  exported: null as unknown,
  mode: "latest",
  setMode: vi.fn(),
  load: vi.fn(),
  record: vi.fn(),
  recent: null as unknown,
}));
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams() }));
vi.mock("../hooks/use-search", () => ({
  useExecuteSearch: () => ({ mutateAsync: mocks.mutateAsync }),
}));
vi.mock("../hooks/use-saved-searches", () => ({ useSavedSearches: () => ({ data: [] }) }));
vi.mock("../hooks/use-recent-searches", () => ({ useRecordRecentSearch: () => mocks.record }));
vi.mock("./search/recent-searches-menu", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./search/recent-searches-menu")>()),
  RecentSearchesMenu: ({ onPick }: { onPick: (search: unknown) => void }) => (
    <button type="button" onClick={() => onPick(mocks.recent)}>
      Run recent
    </button>
  ),
}));
vi.mock("../hooks/use-projects", () => ({ useProjects: () => ({ data: [] }) }));
vi.mock("../hooks/use-collections", () => ({ useCollections: () => ({ data: [] }) }));
vi.mock("@/features/tagging/hooks/use-tags", () => ({ useTags: () => ({ data: [] }) }));
vi.mock("@/features/screening-assay/hooks/use-protocols", () => ({
  useProtocols: () => ({ data: [] }),
}));
vi.mock("../hooks/use-report-config", () => ({
  useReportConfig: () => ({
    config: { imageSize: "small", visibleFields: { structure: [], properties: [], molecule: [] } },
    loadFromSavedSearch: mocks.load,
  }),
}));
vi.mock("../lib/use-aggregation-mode", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/use-aggregation-mode")>()),
  useAggregationMode: () => ({ mode: mocks.mode, setMode: mocks.setMode }),
}));
vi.mock("./search/search-form", () => ({
  SEARCH_PAGE_SIZE: 100,
  SearchForm: ({
    onSearch,
    onReset,
    collapsed,
    headerActions,
  }: {
    onSearch: (q: SearchQuery, c: string[]) => void;
    onReset: () => void;
    collapsed: boolean;
    headerActions?: ReactNode;
  }) => (
    <div>
      {headerActions}
      <span>{collapsed ? "Filters collapsed" : "Filters expanded"}</span>
      {["A", "B"].map((value) => (
        <button
          key={value}
          type="button"
          onClick={() =>
            onSearch(
              { criteria: [{ type: "text", field: "name", operator: "contains", value }] },
              [],
            )
          }
        >
          Search {value}
        </button>
      ))}
      <button type="button" onClick={onReset}>
        Reset
      </button>
    </div>
  ),
}));
vi.mock("./search/results-grid", () => ({
  ResultsGrid: ({
    results,
    aggregationMode,
    toolbarLeft,
    summary,
    footer,
    onSortChange,
    buildExportRequest,
    onRowClick,
  }: {
    onRowClick?: (row: { id: string; name: string }, colId?: string) => void;
    results: { id: string; name: string }[];
    aggregationMode: string;
    toolbarLeft: ReactNode;
    summary: ReactNode;
    footer: ReactNode;
    onSortChange?: (sortBy: string | undefined, sortDir: "asc" | "desc") => void;
    buildExportRequest?: (format: string) => { payload: Record<string, unknown> } | null;
  }) => (
    <div data-testid="results" data-mode={aggregationMode}>
      {toolbarLeft}
      {summary}
      {results.map((r) => (
        <span key={r.id}>{r.name}</span>
      ))}
      {footer}
      <button type="button" onClick={() => onSortChange?.("drc:rd-1", "desc")}>
        Sort IC50
      </button>
      <button type="button" onClick={() => onRowClick?.(results[0], "drc:rd-1:plot@cond:1 mM")}>
        Open 1 mM plot
      </button>
      <button
        type="button"
        onClick={() => {
          mocks.exported = buildExportRequest?.("csv") ?? null;
        }}
      >
        Export CSV
      </button>
    </div>
  ),
}));
vi.mock("./search/results-toolbar", () => ({
  ResultsToolbarLeft: ({ resultCount }: { resultCount: number | null }) => (
    <span>{resultCount ?? "Unknown"} results</span>
  ),
  ResultsToolbarActions: () => null,
  ResultsViewControls: () => null,
  ResultsSelectionActions: () => null,
}));
const sheetProps = vi.hoisted(() => [] as Array<Record<string, unknown>>);
vi.mock("./search/compound-detail-sheet", () => ({
  CompoundDetailSheet: (props: Record<string, unknown>) => {
    sheetProps.push(props);
    return null;
  },
}));
vi.mock("./search/report-customizer", () => ({ ReportCustomizer: () => null }));
vi.mock("./search/save-search-dialog", () => ({ SaveSearchDialog: () => null }));
vi.mock("./search/search-structure-reference", () => ({ SearchStructureReference: () => null }));
vi.mock("@/shared/components/collection-picker-dialog", () => ({
  CollectionPickerDialog: () => null,
}));

import { SearchPage } from "./search-page";

function deferred() {
  let resolve!: (value: unknown) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
const response = (name: string) => ({
  items: [{ id: name, name }],
  next_cursor: null,
  total_count: 1,
});

beforeEach(() => {
  vi.clearAllMocks();
  mocks.mode = "latest";
});

describe("search result provenance", () => {
  it("preserves the initial total when later pages omit it", async () => {
    mocks.mutateAsync
      .mockResolvedValueOnce({
        ...response("Compound A"),
        total_count: 201,
        next_cursor: "page-2",
      })
      .mockResolvedValueOnce({ ...response("Compound B"), total_count: null });
    render(<SearchPage />);
    fireEvent.click(screen.getByText("Search A"));
    await screen.findByText("Compound A");
    expect(screen.getByText("201 results")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Load More"));
    await screen.findByText("Compound B");
    expect(screen.getByText("Compound A")).toBeInTheDocument();
    expect(screen.getByText("201 results")).toBeInTheDocument();
    expect(screen.queryByText("Load More")).not.toBeInTheDocument();
    expect(mocks.mutateAsync.mock.calls.at(-1)?.[0].cursor).toBe("page-2");
  });
  it("retains the successful query and rows during a failed rerun, then retries the failed query", async () => {
    mocks.mutateAsync.mockResolvedValueOnce(response("Compound A"));
    render(<SearchPage />);
    fireEvent.click(screen.getByText("Search A"));
    await screen.findByText("Compound A");
    expect(screen.getByText("Filters collapsed")).toBeInTheDocument();
    const pending = deferred();
    mocks.mutateAsync.mockReturnValueOnce(pending.promise);
    fireEvent.click(screen.getByText("Search B"));
    expect(screen.getByText(/Updating results/)).toBeInTheDocument();
    expect(screen.getByText(/Name contains “A”/)).toBeInTheDocument();
    expect(screen.queryByText(/Name contains “B”/)).not.toBeInTheDocument();
    await act(async () => pending.reject(new Error("Search service unavailable")));
    expect(screen.getByRole("alert")).toHaveTextContent("Search service unavailable");
    expect(screen.getByText("Compound A")).toBeInTheDocument();
    mocks.mutateAsync.mockResolvedValueOnce(response("Compound B"));
    fireEvent.click(screen.getByText("Retry"));
    await screen.findByText("Compound B");
    expect(screen.getByText(/Name contains “B”/)).toBeInTheDocument();
    expect(mocks.mutateAsync.mock.calls.at(-1)?.[0].input.query.criteria[0].value).toBe("B");
  });
  it("does not restore results when a request completes after Reset", async () => {
    const pending = deferred();
    mocks.mutateAsync.mockReturnValueOnce(pending.promise);
    render(<SearchPage />);
    fireEvent.click(screen.getByText("Search A"));
    fireEvent.click(screen.getByText("Reset"));
    await act(async () => pending.resolve(response("Stale compound")));
    expect(screen.queryByText("Stale compound")).not.toBeInTheDocument();
    expect(screen.getByText("Filters expanded")).toBeInTheDocument();
  });
  it("ignores an older response that arrives after the newer search", async () => {
    const older = deferred();
    const newer = deferred();
    mocks.mutateAsync.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise);
    render(<SearchPage />);
    fireEvent.click(screen.getByText("Search A"));
    fireEvent.click(screen.getByText("Search B"));
    await act(async () => newer.resolve(response("New compound")));
    await act(async () => older.resolve(response("Old compound")));
    expect(screen.getByText("New compound")).toBeInTheDocument();
    expect(screen.queryByText("Old compound")).not.toBeInTheDocument();
    expect(screen.getByText(/Name contains “B”/)).toBeInTheDocument();
  });
  it("keeps the executed aggregation on the grid when changing aggregation fails", async () => {
    mocks.mutateAsync.mockResolvedValueOnce(response("Compound A"));
    const view = render(<SearchPage />);
    fireEvent.click(screen.getByText("Search A"));
    await screen.findByText("Compound A");
    mocks.mutateAsync.mockRejectedValueOnce(new Error("Aggregation unavailable"));
    mocks.mode = "gmean";
    view.rerender(<SearchPage />);
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("Aggregation unavailable"),
    );
    expect(screen.getByTestId("results")).toHaveAttribute("data-mode", "latest");
  });
});

describe("server-side sort", () => {
  it("re-runs the search from the first page sorted by the clicked column", async () => {
    mocks.mutateAsync
      .mockResolvedValueOnce({ ...response("Compound A"), next_cursor: "page-2" })
      .mockResolvedValueOnce(response("Compound B"));
    render(<SearchPage />);
    fireEvent.click(screen.getByText("Search A"));
    await screen.findByText("Compound A");
    fireEvent.click(screen.getByText("Sort IC50"));
    await screen.findByText("Compound B");
    const call = mocks.mutateAsync.mock.calls.at(-1)?.[0];
    expect(call.cursor).toBeUndefined();
    expect([call.sort_by, call.sort_dir]).toEqual(["drc:rd-1", "desc"]);
  });

  it("opens the drawer on the column that was clicked", async () => {
    mocks.mutateAsync.mockResolvedValueOnce(response("Compound A"));
    render(<SearchPage />);
    fireEvent.click(screen.getByText("Search A"));
    await screen.findByText("Compound A");
    fireEvent.click(screen.getByText("Open 1 mM plot"));
    expect(sheetProps.at(-1)?.focusColumn).toBe("drc:rd-1:plot@cond:1 mM");
  });

  it("keeps the sort when loading more", async () => {
    mocks.mutateAsync
      .mockResolvedValueOnce(response("Compound A"))
      .mockResolvedValueOnce({ ...response("Compound B"), next_cursor: "r1:0:b" })
      .mockResolvedValueOnce(response("Compound C"));
    render(<SearchPage />);
    fireEvent.click(screen.getByText("Search A"));
    await screen.findByText("Compound A");
    fireEvent.click(screen.getByText("Sort IC50"));
    await screen.findByText("Compound B");
    fireEvent.click(screen.getByText("Load More"));
    await screen.findByText("Compound C");
    const call = mocks.mutateAsync.mock.calls.at(-1)?.[0];
    expect([call.cursor, call.sort_by]).toEqual(["r1:0:b", "drc:rd-1"]);
  });

  it("starts over when the next page's cursor no longer exists", async () => {
    mocks.mutateAsync
      .mockResolvedValueOnce({ ...response("Compound A"), next_cursor: "r1:0:a" })
      .mockRejectedValueOnce(new Error("API error: 422 — Results changed — run the search again"))
      .mockResolvedValueOnce(response("Compound Z"));
    render(<SearchPage />);
    fireEvent.click(screen.getByText("Search A"));
    await screen.findByText("Compound A");
    fireEvent.click(screen.getByText("Load More"));
    await screen.findByText("Compound Z");
    expect(mocks.mutateAsync.mock.calls.at(-1)?.[0].cursor).toBeUndefined();
  });

  it("exports with the grid's sort", async () => {
    mocks.mutateAsync
      .mockResolvedValueOnce(response("Compound A"))
      .mockResolvedValueOnce(response("Compound B"));
    render(<SearchPage />);
    fireEvent.click(screen.getByText("Search A"));
    await screen.findByText("Compound A");
    fireEvent.click(screen.getByText("Sort IC50"));
    await screen.findByText("Compound B");
    fireEvent.click(screen.getByText("Export CSV"));
    expect(mocks.exported).toMatchObject({
      payload: {
        sort_by: "drc:rd-1",
        sort_dir: "desc",
        // The summary line above the grid rides along as the PDF's heading.
        summary: expect.stringMatching(/^All (compounds · All )?projects/),
      },
    });
  });
});

describe("sort across searches", () => {
  it("drops a sort whose column the new search no longer has and runs it unsorted", async () => {
    mocks.mutateAsync
      .mockResolvedValueOnce(response("Compound A"))
      .mockResolvedValueOnce(response("Compound B"))
      .mockRejectedValueOnce(new Error("API error: 422 — Unknown sort column for this search"))
      .mockResolvedValueOnce(response("Compound C"));
    render(<SearchPage />);
    fireEvent.click(screen.getByText("Search A"));
    await screen.findByText("Compound A");
    fireEvent.click(screen.getByText("Sort IC50"));
    await screen.findByText("Compound B");
    fireEvent.click(screen.getByText("Search A"));
    await screen.findByText("Compound C");
    const retried = mocks.mutateAsync.mock.calls.at(-1)?.[0];
    expect(retried.sort_by).toBeUndefined();
    expect(screen.queryByText("Search could not be completed")).not.toBeInTheDocument();
    expect(mocks.mutateAsync).toHaveBeenCalledTimes(4);
  });
});

describe("recent searches", () => {
  it("records a search once it completes — with its rule, columns and count — not a next page", async () => {
    mocks.mutateAsync.mockResolvedValueOnce({ ...response("Compound A"), next_cursor: "p2" });
    mocks.mutateAsync.mockResolvedValueOnce(response("Compound B"));
    render(<SearchPage />);
    fireEvent.click(screen.getByText("Search A"));
    await screen.findByText("Compound A");
    expect(mocks.record).toHaveBeenCalledTimes(1);
    expect(mocks.record).toHaveBeenCalledWith({
      query: {
        criteria: [{ type: "text", field: "name", operator: "contains", value: "A" }],
        aggregation: "latest_run",
      },
      columns: expect.objectContaining({ protocolColumns: [] }),
      result_count: 1,
    });
    fireEvent.click(screen.getByText("Load More"));
    await screen.findByText("Compound B");
    expect(mocks.record).toHaveBeenCalledTimes(1);
  });

  it("runs a picked search with its own rule and table set-up", async () => {
    const columns = { protocolColumns: ["drc:abc"], reportConfig: { imageSize: "large" } };
    mocks.recent = {
      id: "r1",
      query: {
        logic: "and",
        criteria: [{ type: "text", field: "name", operator: "contains", value: "C" }],
        aggregation: "geometric_mean",
      },
      columns,
      result_count: 3,
      ran_at: new Date().toISOString(),
    };
    mocks.mutateAsync.mockResolvedValueOnce(response("Compound C"));
    // Like the real URL-backed mode: the rule set on load is the one read back.
    mocks.setMode.mockImplementationOnce((mode: string) => {
      mocks.mode = mode;
    });
    render(<SearchPage />);
    fireEvent.click(screen.getByText("Run recent"));
    await screen.findByText("Compound C");
    const { input } = mocks.mutateAsync.mock.calls[0][0];
    expect(input.query).toEqual({
      logic: "and",
      criteria: [{ type: "text", field: "name", operator: "contains", value: "C" }],
    });
    expect(input.aggregation).toBe("geometric_mean");
    expect(input.protocol_columns).toEqual(["drc:abc"]);
    expect(mocks.load).toHaveBeenCalledWith(columns);
    expect(mocks.setMode).toHaveBeenCalledWith("gmean");
  });
});
