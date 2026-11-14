/**
 * Grid column id → the backend's sort token (`sort_by` on /search/execute).
 *
 * Every sortable search column ranks the WHOLE result set on the server,
 * using the same values its cells show; null = not sortable (structure
 * strings, plots, placeholder columns).
 *
 * Column ids carry a split group last (`drc:<rd>:ic:50@cond:10 µM`), the
 * backend's grammar: `drc:<rd>[:<kind>:<level>][@<group>]`,
 * `rd:<protocol>:<rd>[:<normalization>][@<group>]`, `any`.
 */
export function serverSortToken(colId: string | undefined): string | null {
  if (!colId) return null;
  if (colId === "molecule") return "registration_number";
  if (colId === "similarity" || colId === "lifecycle_stage" || colId === "any") return colId;
  if (colId.startsWith("prop:")) return colId.slice("prop:".length);
  const [base, ...rest] = colId.split("@");
  const group = rest.length ? `@${rest.join("@")}` : "";
  if (base.startsWith("rd:")) return `${base}${group}`;
  if (base.startsWith("drc:")) {
    const parts = base.split(":");
    if (parts.length === 3 && parts[2] === "value") return `drc:${parts[1]}${group}`;
    if (parts.length === 4) return `${base}${group}`;
  }
  return null;
}
