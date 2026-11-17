"use client";

import {
  ContextMenuItem,
  ContextMenuLabel,
  ContextMenuSeparator,
  ContextMenuSub,
  ContextMenuSubContent,
  ContextMenuSubTrigger,
} from "@/shared/components/ui/context-menu";
import { showError, showSuccess } from "@/shared/lib/toast";
import { Ban, Copy, ExternalLink, Focus, RotateCcw, ScanSearch } from "lucide-react";
import Link from "next/link";
import { formatPlateValue } from "../lib/plate-map-values";
import { replicateWells } from "../lib/replicate-wells";
import type { PlateData, PlateMapWell } from "../types";

export function PlateWellMenu({
  plate,
  well,
  plates,
  excluded,
  rawValue,
  computedValue,
  rawLabel,
  computedLabel,
  doseUnit,
  canFlag,
  flagPending,
  flagUnavailableReason,
  onInspect,
  onFlag,
  onCustomReason,
  onHighlight,
}: {
  plate: PlateData;
  well: PlateMapWell;
  plates: PlateData[];
  excluded: boolean;
  rawValue: number | undefined;
  computedValue: number | undefined;
  rawLabel: string;
  computedLabel: string;
  doseUnit: string;
  canFlag: boolean;
  flagPending: boolean;
  flagUnavailableReason: string | null;
  onInspect: () => void;
  onFlag: (outlier: boolean, reason: string) => void;
  onCustomReason: (outlier: boolean) => void;
  onHighlight: (kind: "compound" | "replicates") => void;
}) {
  const replicates = replicateWells(plates, well);
  const canChangeFlag = canFlag && (rawValue != null || excluded) && !flagPending;
  const reasons = excluded
    ? ["Reviewed — valid measurement", "Exclusion applied in error"]
    : [
        "Dispensing failure",
        "Bubble or optical artefact",
        "Precipitation / insolubility",
        "Contamination",
      ];
  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      showSuccess("Copied to clipboard");
    } catch {
      showError("Could not copy to clipboard");
    }
  };
  const values = [
    [
      "Plate",
      "Well",
      "Compound",
      "Batch",
      `Concentration (${doseUnit})`,
      rawLabel,
      computedLabel,
      "Excluded from QC",
    ],
    [
      plate.plate_number,
      well.position_label,
      well.registration_number ?? well.molecule_name ?? "",
      well.batch_number ?? "",
      well.dose ?? "",
      rawValue ?? "",
      computedValue ?? "",
      excluded ? "Yes" : "No",
    ],
  ]
    .map((row) => row.map((value) => String(value).replace(/[\t\r\n]/g, " ")).join("\t"))
    .join("\n");
  return (
    <>
      <ContextMenuLabel>
        Plate {plate.plate_number} · {well.position_label}
      </ContextMenuLabel>
      <div className="max-w-72 space-y-1 px-2 pb-2 text-xs text-muted-foreground">
        <p className="capitalize">
          {well.well_type.replace(/_/g, " ")}
          {excluded ? " · excluded from QC" : ""}
        </p>
        {well.registration_number && (
          <p>
            {well.registration_number}
            {well.batch_number ? ` · ${well.batch_number}` : ""}
          </p>
        )}
        {well.dose != null && (
          <p>
            {formatPlateValue(well.dose)} {doseUnit}
          </p>
        )}
        {rawValue != null && (
          <p>
            {rawLabel}: {formatPlateValue(rawValue)}
          </p>
        )}
        {computedValue != null && (
          <p>
            {computedLabel}: {formatPlateValue(computedValue)}
          </p>
        )}
      </div>
      <ContextMenuItem onSelect={onInspect}>
        <ScanSearch /> Inspect well and replicates
      </ContextMenuItem>
      <ContextMenuSub>
        <ContextMenuSubTrigger disabled={!canChangeFlag}>
          {excluded ? <RotateCcw /> : <Ban />}
          {excluded ? "Restore to QC" : "Exclude from QC"}
        </ContextMenuSubTrigger>
        <ContextMenuSubContent>
          <ContextMenuLabel>
            {excluded ? "Reason for restoring" : "Reason for exclusion"}
          </ContextMenuLabel>
          <p className="max-w-64 px-2 pb-2 text-xs text-muted-foreground">
            Applies to all raw readouts at this well. Recalculates the run.
          </p>
          {reasons.map((reason) => (
            <ContextMenuItem key={reason} onSelect={() => onFlag(!excluded, reason)}>
              {reason}
            </ContextMenuItem>
          ))}
          <ContextMenuSeparator />
          <ContextMenuItem onSelect={() => onCustomReason(!excluded)}>
            Other reason…
          </ContextMenuItem>
        </ContextMenuSubContent>
      </ContextMenuSub>
      {flagUnavailableReason && (
        <p className="max-w-72 px-2 py-1 text-xs text-muted-foreground">{flagUnavailableReason}</p>
      )}
      {canFlag && rawValue == null && !excluded && (
        <p className="px-2 py-1 text-xs text-muted-foreground">No raw measurement to exclude.</p>
      )}
      <ContextMenuSeparator />
      <ContextMenuItem disabled={!well.molecule_id} onSelect={() => onHighlight("compound")}>
        <Focus /> Highlight same compound
      </ContextMenuItem>
      <ContextMenuItem disabled={replicates.length < 2} onSelect={() => onHighlight("replicates")}>
        <Focus /> Highlight replicates ({replicates.length})
      </ContextMenuItem>
      {well.molecule_id && (
        <ContextMenuItem asChild>
          <Link href={`/compounds/${well.molecule_id}`}>
            <ExternalLink /> Open compound
          </Link>
        </ContextMenuItem>
      )}
      {well.batch_id && (
        <ContextMenuItem asChild>
          <Link href={`/inventory/batches/${well.batch_id}`}>
            <ExternalLink /> Open batch
          </Link>
        </ContextMenuItem>
      )}
      <ContextMenuSeparator />
      <ContextMenuSub>
        <ContextMenuSubTrigger>
          <Copy /> Copy
        </ContextMenuSubTrigger>
        <ContextMenuSubContent>
          <ContextMenuItem
            onSelect={() => void copy(`Plate ${plate.plate_number} · ${well.position_label}`)}
          >
            Well address
          </ContextMenuItem>
          <ContextMenuItem onSelect={() => void copy(values)}>
            Well values (spreadsheet)
          </ContextMenuItem>
          <ContextMenuItem
            disabled={!well.registration_number}
            onSelect={() => void copy(well.registration_number ?? "")}
          >
            Compound ID
          </ContextMenuItem>
          <ContextMenuItem disabled={!well.smiles} onSelect={() => void copy(well.smiles ?? "")}>
            SMILES
          </ContextMenuItem>
        </ContextMenuSubContent>
      </ContextMenuSub>
    </>
  );
}
