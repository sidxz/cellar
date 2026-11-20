import type { PivotRow } from "../lib/readout-data-pivot";
import type { PlateMapResponse } from "../types";

export interface ReadoutTableRow extends PivotRow {
  plateLabel: string | null;
  position: string | null;
  positionOrder: number | null;
  dose: number | null;
  doseUnit: string;
}

/** Join by well id, so repeated compound rows retain their own tested dose. */
export function readoutTableRows(rows: PivotRow[], plateMap?: PlateMapResponse): ReadoutTableRow[] {
  const wells = new Map(
    plateMap?.plates.flatMap((plate) =>
      plate.wells.map((well) => {
        const rowNumber = [...well.row.toUpperCase()].reduce(
          (value, letter) => value * 26 + letter.charCodeAt(0) - 64,
          0,
        );
        return [
          well.well_id,
          {
            plateLabel: plate.registered_plate_barcode || `Plate ${plate.plate_number}`,
            position: well.position_label || well.position,
            positionOrder: plate.plate_number * 1_000_000 + rowNumber * 1_000 + well.column,
            dose: well.dose ?? null,
          },
        ] as const;
      }),
    ),
  );
  return rows
    .map((row) => ({
      ...row,
      plateLabel: null,
      position: null,
      positionOrder: null,
      dose: null,
      ...((row.wellId && wells.get(row.wellId)) || {}),
      doseUnit: plateMap?.dose_unit ?? "",
    }))
    .toSorted(
      (a, b) =>
        a.registrationNumber.localeCompare(b.registrationNumber, undefined, { numeric: true }) ||
        a.batchNumber.localeCompare(b.batchNumber, undefined, { numeric: true }) ||
        (a.positionOrder ?? Number.MAX_SAFE_INTEGER) - (b.positionOrder ?? Number.MAX_SAFE_INTEGER),
    );
}
