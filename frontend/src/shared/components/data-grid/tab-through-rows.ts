import type { GridApi } from "ag-grid-community";
import type { KeyboardEvent } from "react";

// A grid whose cells take no focus (``suppressCellFocus``) still has links and buttons in
// them. AG Grid's own Tab looks for the next cell to focus, finds none it may and cancels the
// key, and the browser's Tab would stop on every row (rows are tab stops of their own) in DOM
// order, not the order shown. Put ``tabThroughRows`` on the grid's wrapper as a capture-phase
// key handler instead.

const TABBABLE = [
  "a[href]",
  "button:not(:disabled)",
  "input:not(:disabled)",
  "select:not(:disabled)",
  '[tabindex]:not([tabindex="-1"])',
];
/** Controls inside rows (a row's own tab stop not included). */
const ROW_CONTROLS = TABBABLE.map((s) => `.ag-row ${s}`).join(",");

/** The rows' controls in reading order: row by row, the pinned rows first, and within a row
 * its left-pinned, centre and right cells. AG Grid renders each of those in a container of its
 * own, so the DOM (the browser's Tab order) walks one container's rows before the next's. */
function rowControls(root: HTMLElement): HTMLElement[] {
  const byRow = new Map<string, HTMLElement[]>();
  for (const el of root.querySelectorAll<HTMLElement>(ROW_CONTROLS)) {
    const row = el.closest(".ag-row") as HTMLElement;
    const key = `${row.closest(".ag-floating-top") ? 0 : 1}:${row.getAttribute("row-index")}`;
    byRow.set(key, [...(byRow.get(key) ?? []), el]);
  }
  const rank = (key: string) => {
    const [section, index] = key.split(":");
    return Number(section) * 1e9 + Number(index.replace(/^t-/, ""));
  };
  return [...byRow.entries()].sort(([a], [b]) => rank(a) - rank(b)).flatMap(([, els]) => els);
}

/** The first control after the rows (the pager's, else the page's next), where Tab from the
 * last row goes. */
function afterRows(root: HTMLElement): HTMLElement | undefined {
  const body = root.querySelector(".ag-body");
  if (!body) return undefined;
  return [...document.querySelectorAll<HTMLElement>(TABBABLE.join(","))].find(
    (el) =>
      !body.contains(el) &&
      !!(body.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) &&
      !el.classList.contains("ag-tab-guard") &&
      !el.closest(".ag-hidden") && // a grid without pages keeps a hidden pager
      el.getAttribute("aria-disabled") !== "true",
  );
}

/** Tab and Shift+Tab through the table: from the last column's header into the first row,
 * row by row through each row's controls ("Selected (n)" and its rows included), past the last
 * row on to the pager, and back the same way. Anything else is left to the grid and the
 * browser. */
export function tabThroughRows(e: KeyboardEvent<HTMLElement>, api: GridApi | undefined) {
  if (e.key !== "Tab" || e.altKey || e.ctrlKey || e.metaKey || !api) return;
  const root = e.currentTarget;
  const target = e.target as HTMLElement;
  const back = e.shiftKey;
  const controls = rowControls(root);
  const lastColumn = api.getAllDisplayedColumns().at(-1);
  const after = afterRows(root);
  let next: HTMLElement | "header" | undefined;
  if (target.closest(".ag-header-cell")) {
    const last =
      target.closest(".ag-header-cell")?.getAttribute("col-id") === lastColumn?.getColId();
    if (!back && last) next = controls[0];
  } else if (target === after) {
    if (back) next = controls.at(-1);
  } else {
    const k = controls.indexOf(target);
    if (k < 0) return;
    next = controls[k + (back ? -1 : 1)] ?? (back ? "header" : after);
  }
  if (!next) return;
  e.preventDefault();
  e.stopPropagation(); // the grid's own Tab handling never runs
  if (next !== "header") next.focus();
  else if (lastColumn) api.setFocusedHeader(lastColumn);
}

/** Shift+Tab into a grid from below lands on its last row's last control, as Tab would leave
 * it; with a pager, or no control in the rows, the grid decides (its pager, else its last
 * header). For ``focusGridInnerElement``; true when it moved focus. */
export function focusFromBelow(root: HTMLElement | null, fromBottom: boolean): boolean {
  if (!root || !fromBottom || root.querySelector(".ag-paging-panel:not(.ag-hidden)")) return false;
  const last = rowControls(root).at(-1);
  last?.focus();
  return !!last;
}
