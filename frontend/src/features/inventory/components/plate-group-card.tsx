"use client";

import { formatDate } from "@/shared/lib/format-date";
import type { PlateGroupNode } from "../hooks/use-plate-groups";
import { formatInitial } from "./plate-group-details";
import { formatLabel, groupTypeColor } from "./plate-group-tree-utils";

export const CARD_WIDTH = 270;
export const CARD_HEIGHT = 210;

export interface PlateGroupCardProps {
  node: PlateGroupNode;
  locationName: string | null;
  selected: boolean;
  onSelect: () => void;
  onRequestLoan: () => void;
}

/** The HTML body of a tree node — rendered inside an SVG <foreignObject>. */
export function PlateGroupCard({
  node,
  locationName,
  selected,
  onSelect,
  onRequestLoan,
}: PlateGroupCardProps) {
  const headerBg = groupTypeColor(node.group_type);
  const rows: string[] = [];
  const fmt = formatLabel(node.plate_format);
  if (fmt || node.scientist) rows.push([fmt, node.scientist].filter(Boolean).join(" · "));
  if (locationName) rows.push(locationName);
  if (node.initial_volume_ul != null || node.initial_concentration_mm != null) {
    rows.push(`Initial: ${formatInitial(node.initial_volume_ul, node.initial_concentration_mm)}`);
  }
  if (node.compound_count != null)
    rows.push(`${node.compound_count.toLocaleString("en-US")} compounds`);
  rows.push(`${node.plate_count} plate${node.plate_count === 1 ? "" : "s"}`);
  rows.push(`created ${formatDate(node.created_at)}`);

  return (
    <div
      title={node.description ?? node.name}
      className={`flex h-full flex-col overflow-hidden rounded-md border bg-card text-card-foreground shadow-sm ${selected ? "ring-2 ring-primary" : ""}`}
      data-testid={`group-card-${node.id}`}
    >
      <button
        type="button"
        onClick={onSelect}
        className="truncate px-2 py-1 text-left text-sm font-semibold text-neutral-900"
        style={{ background: headerBg }}
      >
        {node.name}
        {node.group_type ? (
          <span className="ml-2 text-xs font-normal opacity-80">{node.group_type}</span>
        ) : null}
      </button>
      <ul className="flex-1 space-y-0.5 px-2 py-1 text-xs text-muted-foreground">
        {rows.map((r) => (
          <li key={r} className="truncate">
            {r}
          </li>
        ))}
      </ul>
      <div className="flex gap-3 border-t px-2 py-1 text-xs">
        <button type="button" className="text-primary hover:underline" onClick={onSelect}>
          Details
        </button>
        {node.plate_count > 0 ? (
          <button type="button" className="text-primary hover:underline" onClick={onRequestLoan}>
            Request loan
          </button>
        ) : null}
      </div>
    </div>
  );
}
