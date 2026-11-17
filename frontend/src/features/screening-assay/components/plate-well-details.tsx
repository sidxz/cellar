"use client";

import { StructureThumbnail } from "@/shared/components/chemistry";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/shared/components/ui/sheet";
import Link from "next/link";
import { formatPlateValue } from "../lib/plate-map-values";
import { replicateWells } from "../lib/replicate-wells";
import type { DoseResponseCurve, PlateData, PlateMapWell } from "../types";
import { DoseResponseChartView } from "./dose-response-figure";
import { OutlierFlagPopover } from "./outlier-flag-popover";

export function PlateWellDetails({
  plate,
  well,
  plates,
  rawValues,
  computedValues,
  responseValues,
  responseLabel,
  rawUnit,
  computedUnit,
  doseUnit,
  outliers,
  curves,
  canFlag,
  flagPending,
  reasonRequired,
  onFlag,
  onClose,
}: {
  plate: PlateData;
  well: PlateMapWell;
  plates: PlateData[];
  rawValues: ReadonlyMap<string, number>;
  computedValues: ReadonlyMap<string, number>;
  responseValues: ReadonlyMap<string, number>;
  responseLabel: string;
  rawUnit: string | null;
  computedUnit: string;
  doseUnit: string;
  outliers: ReadonlySet<string>;
  curves: DoseResponseCurve[];
  canFlag: boolean;
  flagPending: boolean;
  reasonRequired: boolean;
  onFlag: (well: PlateMapWell, outlier: boolean, reason: string | null) => void;
  onClose: () => void;
}) {
  const excluded = outliers.has(well.well_id);
  const raw = rawValues.get(well.well_id);
  const computed = computedValues.get(well.well_id);
  const aliases = [...new Set([well.molecule_name, ...(well.synonyms ?? [])].filter(Boolean))];
  const relatedCurves = well.molecule_id
    ? curves.filter(
        (curve) =>
          curve.molecule_id === well.molecule_id &&
          (well.batch_id
            ? curve.batch_id === well.batch_id
            : !!well.batch_number && curve.batch_number === well.batch_number),
      )
    : [];
  const replicates = replicateWells(plates, well);

  return (
    <Sheet
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader className="border-b pr-10">
          <SheetTitle>
            Plate {plate.plate_number} · {well.position_label}
          </SheetTitle>
          <SheetDescription>
            Compound, concentration, and response at this position.
          </SheetDescription>
        </SheetHeader>
        <div className="space-y-5 px-4 pb-6">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline" className="capitalize">
                {well.well_type.replace(/_/g, " ")}
              </Badge>
              {excluded && <Badge variant="destructive">Excluded from QC</Badge>}
            </div>
            {well.molecule_id ? (
              <Link
                href={`/compounds/${well.molecule_id}`}
                className="text-lg font-semibold text-primary hover:underline"
              >
                {well.registration_number ??
                  well.molecule_name ??
                  well.batch_number ??
                  "Open compound"}
              </Link>
            ) : (
              <p className="text-sm font-medium">{well.label ?? "No compound assigned"}</p>
            )}
            {aliases.length > 0 && (
              <p className="text-sm text-muted-foreground">{aliases.join(" · ")}</p>
            )}
            {well.smiles && (
              <div className="flex justify-center rounded-md border bg-white p-3">
                <StructureThumbnail smiles={well.smiles} size={180} />
              </div>
            )}
          </div>
          <dl className="grid grid-cols-2 gap-4 rounded-md border p-3 text-sm">
            <div>
              <dt className="text-xs text-muted-foreground">Batch</dt>
              <dd className="mt-1 break-all tabular-nums">{well.batch_number ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Concentration</dt>
              <dd className="mt-1 tabular-nums">
                {well.dose == null ? "—" : `${formatPlateValue(well.dose)} ${doseUnit}`}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Raw response</dt>
              <dd className="mt-1 tabular-nums">
                {raw == null
                  ? "Unavailable"
                  : `${formatPlateValue(raw)}${rawUnit ? ` ${rawUnit}` : ""}`}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">{computedUnit}</dt>
              <dd className="mt-1 tabular-nums">
                {computed == null ? "Unavailable" : formatPlateValue(computed)}
              </dd>
            </div>
          </dl>
          {well.note && <p className="text-sm text-muted-foreground">{well.note}</p>}
          {canFlag && (raw != null || excluded) && (
            <OutlierFlagPopover
              flagged={excluded}
              title={`Plate ${plate.plate_number} · ${well.position_label}`}
              pending={flagPending}
              reasonRequired={reasonRequired}
              onSubmit={(reason) => onFlag(well, !excluded, reason)}
            >
              <Button size="sm" variant="outline">
                Outlier options
              </Button>
            </OutlierFlagPopover>
          )}
          {replicates.length > 1 && (
            <section className="space-y-2">
              <h3 className="text-sm font-semibold">
                {well.batch_id || well.batch_number
                  ? "Same sample and concentration"
                  : "Same compound and concentration"}{" "}
                · {replicates.length} wells
              </h3>
              <div className="overflow-auto rounded-md border">
                <table className="w-full text-sm">
                  <thead className="bg-muted/30 text-left text-xs text-muted-foreground">
                    <tr>
                      <th className="px-3 py-2 font-medium">Plate / well</th>
                      <th className="px-3 py-2 text-right font-medium">{responseLabel}</th>
                      <th className="px-3 py-2 font-medium">Outlier flag</th>
                    </tr>
                  </thead>
                  <tbody>
                    {replicates.map((replicate) => {
                      const value = responseValues.get(replicate.well.well_id);
                      return (
                        <tr key={replicate.well.well_id} className="border-t">
                          <td className="px-3 py-2">
                            Plate {replicate.plate.plate_number} · {replicate.well.position_label}
                          </td>
                          <td className="px-3 py-2 text-right tabular-nums">
                            {value == null ? "—" : formatPlateValue(value)}
                          </td>
                          <td className="px-3 py-2">
                            {outliers.has(replicate.well.well_id) ? "Excluded" : "—"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          )}
          {relatedCurves.length > 0 && (
            <section className="space-y-2">
              <h3 className="text-sm font-semibold">Dose-response for this sample</h3>
              <DoseResponseChartView curves={relatedCurves} />
            </section>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
