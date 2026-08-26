"use client";

import type { PlateGroupNode } from "../hooks/use-plate-groups";
import { formatInitial, formatLabel, groupTypeColor } from "./plate-group-tree-utils";

export interface PlateGroupCardProps {
  node: PlateGroupNode;
  locationName: string | null;
  /** Total plates in this group's subtree (own + descendants). */
  subtreePlates: number;
  selected: boolean;
  onSelect: () => void;
  onRequestLoan: () => void;
}

/** The HTML body of a set node — rendered inside an SVG <foreignObject>, legacy
 * "name pill + plain rows" style (no card box). */
export function PlateGroupCard({
  node,
  locationName,
  subtreePlates,
  selected,
  onSelect,
  onRequestLoan,
}: PlateGroupCardProps) {
  const pillBg = groupTypeColor(node.group_type);
  const title = node.description ? `${node.name} — ${node.description}` : node.name;
  const rows: string[] = [];
  const fmt = formatLabel(node.plate_format);
  if (fmt || node.scientist) rows.push([fmt, node.scientist].filter(Boolean).join(" · "));
  if (locationName) rows.push(locationName);
  if (node.initial_volume_ul != null || node.initial_concentration_mm != null) {
    rows.push(`Initial: ${formatInitial(node.initial_volume_ul, node.initial_concentration_mm)}`);
  }
  if (node.compound_count != null)
    rows.push(`${node.compound_count.toLocaleString("en-US")} compounds`);
  if (subtreePlates > 0) rows.push(`${subtreePlates} plate${subtreePlates === 1 ? "" : "s"}`);

  return (
    <div className="flex flex-col gap-1" data-testid={`group-card-${node.id}`}>
      <button
        type="button"
        onClick={onSelect}
        title={title}
        className={`w-fit rounded-md px-2 py-0.5 text-left font-semibold text-[15px] leading-tight text-neutral-900 whitespace-normal break-words ${selected ? "ring-2 ring-primary" : ""}`}
        style={{ background: pillBg }}
      >
        {node.name}
      </button>
      <ul className="space-y-0.5 text-[15px] leading-6 text-muted-foreground">
        {rows.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
      <div className="flex gap-3 text-[15px]">
        <button type="button" className="text-primary hover:underline" onClick={onSelect}>
          Details
        </button>
        {subtreePlates > 0 ? (
          <button type="button" className="text-primary hover:underline" onClick={onRequestLoan}>
            Request loan
          </button>
        ) : null}
      </div>
    </div>
  );
}
