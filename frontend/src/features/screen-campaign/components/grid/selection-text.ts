/** "3 selected rows" / "80 selected rows, 74 hidden by filters": what a bulk gesture reaches,
 *  never leaving a ticked row the filters hide unmentioned. */
export function selectionText(selected: number, hidden: number): string {
  const rows = `${selected} selected ${selected === 1 ? "row" : "rows"}`;
  return hidden > 0 ? `${rows}, ${hidden} hidden by filters` : rows;
}
