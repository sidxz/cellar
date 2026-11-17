import type { PlateData, PlateMapWell } from "../types";

/** Replicates share the sample identity, well role and known concentration. */
export function replicateWells(plates: PlateData[], well: PlateMapWell) {
  if (!(well.molecule_id || well.batch_id) || well.dose == null) return [];
  return plates.flatMap((plate) =>
    plate.wells
      .filter(
        (candidate) =>
          candidate.well_type === well.well_type &&
          (well.batch_id
            ? candidate.batch_id === well.batch_id
            : well.batch_number
              ? candidate.batch_number === well.batch_number
              : candidate.molecule_id === well.molecule_id &&
                !candidate.batch_id &&
                !candidate.batch_number) &&
          candidate.dose === well.dose,
      )
      .map((candidate) => ({ plate, well: candidate })),
  );
}
