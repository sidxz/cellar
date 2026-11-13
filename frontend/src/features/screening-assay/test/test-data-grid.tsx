// Test double for the shared DataGrid; tests use it through
// `vi.mock("@/shared/components/data-grid/data-grid", ...)`.
import { type ReactNode, useState } from "react";

interface MockCol {
  headerName?: string;
  hide?: boolean;
  children?: MockCol[];
  valueGetter?: (p: { data: unknown }) => unknown;
  getQuickFilterText?: (p: { data: unknown; value: unknown }) => string;
  valueFormatter?: (p: { data: unknown; value: unknown }) => string;
  cellRenderer?: (p: { data: unknown; value: unknown }) => ReactNode;
  cellClass?: string | ((p: { data: unknown; value: unknown }) => string | undefined);
}
interface MockGridProps {
  rowData: unknown[];
  pinnedTopRowData?: unknown[];
  columnDefs: MockCol[];
  getRowId: (p: { data: unknown }) => string;
  rowClassRules?: Record<string, (p: { data: unknown }) => boolean>;
  onRowClicked?: (e: { data: unknown; event: MouseEvent; api: unknown }) => void;
  onCellKeyDown?: (e: { data: unknown; event: KeyboardEvent; api: unknown }) => void;
  searchPlaceholder?: string | false;
}

/** The grid as a plain table: pinned rows then body rows, through the column
 *  renderers; row clicks reach onRowClicked and key presses onCellKeyDown with
 *  the native event. A search placeholder adds a quick filter over the body,
 *  as AG Grid's: every word must appear in some column's quick-filter text. */
export function TableGrid(props: MockGridProps) {
  const [search, setSearch] = useState("");
  const leaves = props.columnDefs.flatMap((c) => c.children ?? [c]).filter((c) => !c.hide);
  const text = (data: unknown) =>
    leaves
      .map((c) => {
        const value = c.valueGetter?.({ data });
        return c.getQuickFilterText ? c.getQuickFilterText({ data, value }) : String(value ?? "");
      })
      .join(" ")
      .toLowerCase();
  const words = search.toLowerCase().split(/\s+/).filter(Boolean);
  const body = props.rowData.filter((d) => words.every((w) => text(d).includes(w)));
  const api = {
    forEachNodeAfterFilterAndSort: (cb: (n: { data: unknown }) => void) => {
      for (const data of body) cb({ data });
    },
  };
  return (
    <>
      {typeof props.searchPlaceholder === "string" && (
        <input
          placeholder={props.searchPlaceholder}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      )}
      <table>
        <thead>
          <tr>
            {props.columnDefs.map((c, i) => (
              <th key={i}>{c.children ? c.headerName : ""}</th>
            ))}
          </tr>
          <tr>
            {leaves.map((c, i) => (
              <th key={i}>{c.headerName}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {[...(props.pinnedTopRowData ?? []), ...body].map((data) => {
            const id = props.getRowId({ data });
            return (
              <tr
                key={id}
                data-row-id={id}
                className={Object.entries(props.rowClassRules ?? {})
                  .filter(([, rule]) => rule({ data }))
                  .map(([cls]) => cls)
                  .join(" ")}
                tabIndex={-1}
                onClick={(e) => props.onRowClicked?.({ data, event: e.nativeEvent, api })}
                onKeyDown={(e) => props.onCellKeyDown?.({ data, event: e.nativeEvent, api })}
              >
                {leaves.map((c, i) => {
                  const p = { data, value: c.valueGetter?.({ data }) };
                  const cls = typeof c.cellClass === "function" ? c.cellClass(p) : c.cellClass;
                  return (
                    <td key={i} className={cls}>
                      {c.cellRenderer
                        ? c.cellRenderer(p)
                        : c.valueFormatter
                          ? c.valueFormatter(p)
                          : String(p.value ?? "")}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </>
  );
}

/** The grid row whose cell reads exactly `text`. */
export function gridRow(text: string): HTMLTableRowElement {
  const row = [...document.querySelectorAll<HTMLTableRowElement>("tr[data-row-id]")].find((tr) =>
    [...tr.cells].some((td) => td.textContent === text),
  );
  if (!row) throw new Error(`no grid row with ${text}`);
  return row;
}
