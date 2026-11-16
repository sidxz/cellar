import type { Dataset } from "../../types";
import { isComparedValue, missingReason } from "../cross-protocol";
import { categoryLabel, column } from "../dataset";
import { cellText, qualifierText } from "../value-description";
import { fieldLabel } from "./common";

type Line = { label: string; value: string };

/** What a plot's hover card says about row ``i``. */
export interface HoverInfo {
  /** The SMILES to draw, when the row has a structure. */
  structure: string | null;
  /** The compound, else the well's label, else "No compound". */
  title: string;
  /** Run, plate and well, as far as the row has them. */
  place: string;
  /** "Field: value" per field, the plotted ones first, each once. */
  lines: Line[];
}

/** Fields the card's head already shows. */
const HEAD = new Set(["compound", "structure", "molecule_id", "run", "plate", "well"]);

const text = (v: unknown) => (typeof v === "string" && v ? v : null);

/** A field's value as the card shows it: numbers with their qualifier ("> 42.5"); a
 * compared protocol's missing value says why ("Not tested in …"). */
function valueText(ds: Dataset, key: string, i: number): string {
  const v = ds.values[key]?.[i];
  if (typeof v === "number" && Number.isFinite(v)) {
    const q = qualifierText(ds.values[`${key}:q`]?.[i]);
    return q && q !== "=" ? `${q} ${cellText(v)}` : cellText(v);
  }
  if (v == null && isComparedValue(ds, key)) return missingReason(ds, key, i) ?? "No value";
  return categoryLabel(key, v);
}

/** The card of row ``i``: its compound and structure, where it sits, and ``fields``. */
export function hoverInfo(ds: Dataset, i: number, fields: (string | undefined)[]): HoverInfo {
  const at = (key: string) => text(ds.values[key]?.[i]);
  const run = at("run");
  const plate = at("plate");
  // A plate of a multi-run dataset is already "<run> · Plate n".
  const runText = run && !plate?.startsWith(run) ? run : null;
  const place = [runText, [plate, at("well")].filter(Boolean).join(" ")].filter(Boolean);
  const compound = at("compound");
  const label = compound ? null : at("label");
  const lines: Line[] = [];
  for (const key of new Set(fields)) {
    if (!key || HEAD.has(key) || (label && key === "label") || !column(ds, key)) continue;
    lines.push({ label: fieldLabel(ds, key), value: valueText(ds, key, i) });
  }
  return {
    structure: at("structure"),
    title: compound ?? label ?? "No compound",
    place: place.join(" · "),
    lines,
  };
}

/** The part of a Plotly box-hover point the card reads. */
export type BoxHoverPoint = { y?: unknown; data?: { name?: unknown; y?: unknown[] } };

/** A hovered box: its group, median and quartiles as Plotly computed them, and its count.
 * Plotly sends the box's max, upper fence, Q3, median, Q1, lower fence and min; any other
 * set (a mean, another Plotly) is not guessed at. */
export function boxSummary(points: BoxHoverPoint[]): { title: string; lines: Line[] } {
  const data = points[0]?.data;
  const ys = points
    .map((p) => p.y)
    .filter((y): y is number => typeof y === "number")
    .sort((a, b) => b - a);
  const lines: Line[] =
    ys.length === 7
      ? [
          { label: "Median", value: cellText(ys[3]) },
          { label: "Q1 – Q3", value: `${cellText(ys[4])} – ${cellText(ys[2])}` },
        ]
      : [];
  lines.push({ label: "n", value: String(data?.y?.length ?? 0) });
  return { title: String(data?.name ?? ""), lines };
}
