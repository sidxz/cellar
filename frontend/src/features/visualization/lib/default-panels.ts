import type { Appearance, PanelConfig, PanelPatch, PanelType } from "../store/workbench-store";
import type { Dataset, DatasetColumn } from "../types";
import { isCrossProtocol } from "./cross-protocol";
import { categoryColumns, column, valueColumns } from "./dataset";
import { rgroupPositions, rgroupSetOf } from "./derived";

/** The main value: the first numeric readout value column, except that a raw layer gives way
 * to the dataset's first normalized one (% inhibition, % control, Z-score, …) when a readout
 * has one. A potency (no layer) stays first. */
export function numericValueColumn(ds: Dataset): DatasetColumn | undefined {
  const numbers = valueColumns(ds).filter((c) => c.kind === "number");
  const normalized = (c: DatasetColumn) => c.provenance.layer && c.provenance.layer !== "raw";
  // ponytail: the server orders a readout's layers by name, so of two (% inhibition + Z-score)
  // the alphabetically first wins, not the readout's declared primary; carry it if they differ.
  return numbers[0]?.provenance.layer === "raw"
    ? (numbers.find(normalized) ?? numbers[0])
    : numbers[0];
}

/** Fields naming the row itself above Wells: a box or bar of them holds one row each. */
const IDENTITY = new Set(["compound", "batch"]);

/** A compared column's name without its "<protocol> · " prefix. */
const ownLabel = (c: DatasetColumn) =>
  c.group && c.label.startsWith(`${c.group} · `) ? c.label.slice(c.group.length + 3) : c.label;

/** A cross-protocol scatter's axes: the primary protocol's potency (its first p-value, else
 * its first number) on X; on Y the first compared protocol's matching value (same kind,
 * same name if one has it, else the first of that kind), else its first number. */
function compareAxes(ds: Dataset): { x?: string; y?: string } {
  const [primary, compared] = (ds.protocols ?? []).map((p) => p.protocol_id);
  const numbers = valueColumns(ds).filter((c) => c.kind === "number");
  const of = (pid: string) => numbers.filter((c) => c.provenance.protocol_id === pid);
  const mine = of(primary);
  const x = mine.find((c) => c.provenance.aggregation === "p") ?? mine[0];
  const theirs = of(compared);
  const same = theirs.filter((c) => c.provenance.aggregation === x?.provenance.aggregation);
  const y = same.find((c) => x && ownLabel(c) === ownLabel(x)) ?? same[0] ?? theirs[0];
  return { x: x?.key, y: y?.key };
}

/** The fields a newly added panel of ``type`` starts with: numeric fields take the main
 * value (numericValueColumn), category fields well type (else the first category column that is not
 * the row's own identity), and well type colors (and stacks) the plot when the dataset has
 * it. A scatter plots two different fields: well order, or across protocols the compared
 * potencies (see compareAxes), else another numeric readout. An R-group matrix takes R1
 * rows × R2 columns of the first R-groups set and the median of the main value. */
export function panelDefaults(ds: Dataset, type: PanelType): PanelPatch {
  const value = numericValueColumn(ds)?.key;
  const wellType = column(ds, "well_type")?.key;
  const aggregated = ds.level !== "wells";
  const category =
    wellType ?? categoryColumns(ds).find((c) => !(aggregated && IDENTITY.has(c.key)))?.key;
  switch (type) {
    case "scatter": {
      const cross = isCrossProtocol(ds) ? compareAxes(ds) : {};
      const y = cross.y ?? value;
      const other = (key?: string) => (key !== y ? key : undefined);
      // Another readout first: a readout's own siblings (IC50 vs pIC50) only draw a fixed curve.
      const numbers = valueColumns(ds).filter((c) => c.kind === "number" && c.key !== y);
      const readout = y ? column(ds, y)?.provenance.readout_definition_id : undefined;
      return {
        x:
          column(ds, "well_order")?.key ??
          other(cross.x) ??
          (numbers.find((c) => c.provenance.readout_definition_id !== readout) ?? numbers[0])
            ?.key ??
          y,
        y,
        appearance: { colorBy: wellType, shapeBy: wellType },
      };
    }
    case "histogram":
      return { x: value, appearance: { colorBy: wellType } };
    case "bar":
      return { agg: "count", category };
    case "box":
      return { y: value, category };
    case "rgroup-matrix": {
      const positions = rgroupPositions(ds);
      const set = positions.filter((k) => rgroupSetOf(k) === rgroupSetOf(positions[0] ?? ""));
      return { category: set[0], x: set[1] ?? set[0], y: value, agg: "median" };
    }
  }
}

/** The patch that turns panel ``p`` into a ``type`` panel. The measured field carries over
 * (a scatter/bar/box Y is a histogram's X), as do a bar/box group and a scatter's X; fields
 * still missing come from panelDefaults (appearance only where unset), and data fields the
 * new type does not draw are cleared. */
export function retypePanel(ds: Dataset, p: PanelConfig, type: PanelType): PanelPatch {
  const d = panelDefaults(ds, type);
  const value = p.type === "histogram" ? p.x : p.y;
  const appearance = Object.fromEntries(
    Object.entries(d.appearance ?? {}).filter(
      ([k]) => p.appearance[k as keyof Appearance] === undefined,
    ),
  );
  const base: PanelPatch = {
    type,
    x: undefined,
    y: undefined,
    category: undefined,
    logX: undefined,
    logY: undefined,
    appearance,
  };
  switch (type) {
    case "scatter":
      return { ...base, x: p.type === "scatter" ? p.x : d.x, y: value ?? d.y, logY: p.logY };
    case "histogram":
      return { ...base, x: value ?? d.x };
    case "bar":
      return { ...base, category: p.category ?? d.category, agg: p.agg ?? d.agg, y: value };
    case "box":
      return { ...base, category: p.category ?? d.category, y: value ?? d.y, logY: p.logY };
    case "rgroup-matrix":
      return { ...base, category: d.category, x: d.x, y: value ?? d.y, agg: d.agg };
  }
}

/** The panels a fresh workbench opens with: a plate-order scatter of the main value
 * (numericValueColumn) split by plate, or, when nothing numeric exists, a count bar so the chemist
 * still sees something. */
export function defaultPanels(ds: Dataset): Array<{ type: PanelType; defaults: PanelPatch }> {
  if (numericValueColumn(ds)) {
    // Summary results have no well positions: a plate-order scatter would be empty.
    if (!(ds.values.well_order ?? []).some((v) => v != null)) {
      return [{ type: "histogram", defaults: panelDefaults(ds, "histogram") }];
    }
    const scatter = panelDefaults(ds, "scatter");
    return [
      {
        type: "scatter",
        defaults: { ...scatter, appearance: { splitBy: "plate", ...scatter.appearance } },
      },
    ];
  }
  const bar = panelDefaults(ds, "bar");
  return bar.category ? [{ type: "bar", defaults: bar }] : [];
}
