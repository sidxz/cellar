import { SavedViewsListPage } from "@/features/visualization/components/saved-views-list";
import type { SavedViewSummary } from "@/features/visualization/types";
import { act, fireEvent, render, screen } from "@testing-library/react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { describe, expect, it, vi } from "vitest";
import { DataGrid } from "./data-grid";

// The saved views list, the caller this was found on.
vi.mock("next/navigation", () => ({
  usePathname: () => "/assays/visualize",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
vi.mock("@/features/visualization/hooks/use-saved-views", () => ({
  useSavedViews: () => ({
    data: ["Plate QC", "Potency"].map((name, k) => ({
      id: `v${k}`,
      name,
      level: "wells",
      visibility: "private",
      created_by: "u1",
      can_edit: true,
      version: 1,
      updated_at: "2026-11-16T10:00:00Z",
      protocols: [],
    })) satisfies SavedViewSummary[],
    isLoading: false,
    error: null,
  }),
}));
vi.mock("@/features/research-organization/hooks/use-projects", () => ({
  useProjects: () => ({ data: [] }),
}));
vi.mock("@/shared/hooks/use-workspace-members", () => ({
  useMemberNames: () => () => "A. Chen",
}));

/** Tab (Shift+Tab) as a browser presses it: the keydown goes to the focused element and,
 * unless a handler cancels it, focus moves on to the next (previous) element in the
 * document's Tab order — jsdom does only the first half. Returns what holds focus after. */
function pressTab(shiftKey = false): Element | null {
  const from = document.activeElement ?? document.body;
  if (fireEvent.keyDown(from, { key: "Tab", shiftKey })) {
    const tabbable = [...document.body.querySelectorAll<HTMLElement>("*")].filter(
      (el) =>
        el.tabIndex >= 0 &&
        !(el as HTMLButtonElement).disabled &&
        !el.closest(".ag-hidden,[hidden],[inert]"),
    );
    const follows = (el: Element) =>
      !!(from.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING);
    const next = shiftKey
      ? tabbable.filter((el) => el !== from && !follows(el)).at(-1)
      : tabbable.find(follows);
    act(() => (next ?? (from as HTMLElement)).focus());
    if (!next) act(() => (from as HTMLElement).blur());
  }
  return document.activeElement;
}

const nameOf = (el: Element | null) =>
  el?.closest(".ag-header-cell")
    ? `header ${el.textContent?.trim()}`
    : (el?.getAttribute("aria-label") ?? el?.textContent?.trim());
const walk = (steps: number, shiftKey = false) =>
  Array.from({ length: steps }, () => nameOf(pressTab(shiftKey)));

type Row = { name: string };
const rows: Row[] = [{ name: "Alpha" }, { name: "Beta" }];
const columns: ColDef<Row>[] = [
  {
    headerName: "Name",
    field: "name",
    cellRenderer: (p: ICellRendererParams<Row>) => <a href={`/x/${p.value}`}>{p.value}</a>,
  },
  {
    headerName: "Action",
    cellRenderer: (p: ICellRendererParams<Row>) => (
      <button type="button" aria-label={`Open ${p.data?.name}`}>
        Open
      </button>
    ),
  },
];

const around = (grid: React.ReactNode) =>
  render(
    <>
      <button type="button">Before</button>
      {grid}
      <button type="button">After</button>
    </>,
  );

describe("DataGrid keyboard", () => {
  it("tabs from the headers through each row's links and buttons, then on out of the grid", async () => {
    around(<DataGrid<Row> rowData={rows} columnDefs={columns} searchPlaceholder={false} />);
    await screen.findByRole("link", { name: "Alpha" });
    act(() => screen.getByRole("button", { name: "Before" }).focus());
    expect(walk(7)).toEqual([
      "header Name",
      "header Action",
      "Alpha",
      "Open Alpha",
      "Beta",
      "Open Beta",
      "After",
    ]);
    // And back: from below into the last row, from the first row to the last header.
    expect(walk(6, true)).toEqual([
      "Open Beta",
      "Beta",
      "Open Alpha",
      "Alpha",
      "header Action",
      "header Name",
    ]);
  });

  it("tabs in the order the rows are shown, after a sort", async () => {
    around(<DataGrid<Row> rowData={rows} columnDefs={columns} searchPlaceholder={false} />);
    await screen.findByRole("link", { name: "Alpha" });
    const sortByName = () =>
      fireEvent.click(
        document.querySelector('.ag-header-cell[col-id="name"] .ag-header-cell-label') as Element,
      );
    sortByName(); // ascending
    sortByName(); // descending
    act(() => screen.getByRole("link", { name: "Beta" }).focus());
    expect(walk(3)).toEqual(["Open Beta", "Alpha", "Open Alpha"]);
  });

  it("leaves a grid with cell focus to AG Grid: Tab moves cell to cell", async () => {
    around(
      <DataGrid<Row>
        rowData={rows}
        columnDefs={[{ headerName: "Name", field: "name" }, { headerName: "Note" }]}
        searchPlaceholder={false}
        suppressCellFocus={false}
      />,
    );
    const alpha = await screen.findByText("Alpha");
    const cell = alpha.closest(".ag-cell") as HTMLElement;
    act(() => cell.focus());
    expect(fireEvent.keyDown(cell, { key: "Tab" })).toBe(false);
    expect(document.activeElement?.closest(".ag-cell")?.getAttribute("col-id")).toBe("0");
  });

  it("walks the saved views list's links one by one", async () => {
    render(
      <>
        <SavedViewsListPage />
        <button type="button">After</button>
      </>,
    );
    const first = await screen.findByRole("link", { name: "Plate QC" });
    act(() => first.focus());
    expect(walk(2)).toEqual(["Potency", "After"]);
    expect(walk(2, true)).toEqual(["Potency", "Plate QC"]);
  });
});
