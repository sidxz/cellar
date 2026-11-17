"use client";

import Link from "next/link";
import { formatPlateValue, plateCompounds } from "../lib/plate-map-values";
import type { PlateData } from "../types";

export function PlateCompoundsList({
  plate,
  colors,
  doseUnit,
}: {
  plate: PlateData;
  colors: ReadonlyMap<string, string>;
  doseUnit: string;
}) {
  const compounds = plateCompounds(plate);
  if (!compounds.length) return null;

  return (
    <details className="group rounded-md border">
      <summary className="cursor-pointer px-3 py-2 text-sm font-medium text-muted-foreground hover:text-foreground">
        Compounds on plate ({compounds.length})
      </summary>
      <div className="max-h-72 overflow-auto border-t">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-muted text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium">Compound</th>
              <th className="px-2 py-2 font-medium">Batch</th>
              <th className="px-2 py-2 text-right font-medium">Concentration ({doseUnit})</th>
              <th className="px-3 py-2 text-right font-medium">Wells</th>
            </tr>
          </thead>
          <tbody>
            {compounds.map((compound) => {
              const doses = [...compound.doses].sort((a, b) => a - b);
              const concentration = !doses.length
                ? "—"
                : doses.length === 1
                  ? formatPlateValue(doses[0])
                  : `${formatPlateValue(doses[0])}–${formatPlateValue(doses[doses.length - 1])}`;
              return (
                <tr key={compound.id} className="border-t">
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <span
                        className="h-2.5 w-2.5 shrink-0 rounded-sm"
                        style={{ background: colors.get(compound.id) }}
                        aria-hidden
                      />
                      <Link
                        href={`/compounds/${compound.id}`}
                        className="tabular-nums text-primary hover:underline"
                        title={[...compound.aliases].join(" · ")}
                      >
                        {compound.label}
                      </Link>
                    </div>
                  </td>
                  <td className="px-2 py-2 text-muted-foreground">
                    {[...compound.batches].join(", ") || "—"}
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums">{concentration}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{compound.wellCount}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </details>
  );
}
