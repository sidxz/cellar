import type { ReadoutDefinition } from "../types";

export const DELTA_TM_HINT =
  "Typical: outside −2 to 2 °C (Thermo Fisher Protein Thermal Shift guide; MIT nanoDSF SOP)";

export const isDeltaTm = (readout?: Pick<ReadoutDefinition, "melt_config"> | null): boolean =>
  readout?.melt_config?.measure === "delta_tm";

/** A reference line under a criterion on a ΔTm readout. Nothing is filled in. */
export function DeltaTmHint({
  readout,
}: { readout?: Pick<ReadoutDefinition, "melt_config"> | null }) {
  if (!isDeltaTm(readout)) return null;
  return <p className="text-[10px] text-muted-foreground italic">{DELTA_TM_HINT}</p>;
}
