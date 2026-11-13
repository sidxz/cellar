// Test double for the shared DataGrid; tests use it through
// `vi.mock("@/shared/components/data-grid/data-grid", ...)`.
import type { ReactNode } from "react";

interface MockCol {
  headerName?: string;
  hide?: boolean;
  children?: MockCol[];
  valueGetter?: (p: { data: unknown }) => unknown;
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
}

/** The grid as a plain table: pinned rows then body rows, through the column
 *  renderers, and row clicks reach onRowClicked with the native event. */
export function TableGrid(props: MockGridProps) {
  const leaves = props.columnDefs.flatMap((c) => c.children ?? [c]).filter((c) => !c.hide);
  const api = {
    forEachNodeAfterFilterAndSort: (cb: (n: { data: unknown }) => void) => {
      for (const data of props.rowData) cb({ data });
    },
  };
  return (
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
        {[...(props.pinnedTopRowData ?? []), ...props.rowData].map((data) => {
          const id = props.getRowId({ data });
          return (
            <tr
              key={id}
              data-row-id={id}
              className={Object.entries(props.rowClassRules ?? {})
                .filter(([, rule]) => rule({ data }))
                .map(([cls]) => cls)
                .join(" ")}
              onClick={(e) => props.onRowClicked?.({ data, event: e.nativeEvent, api })}
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
