/**
 * Resolve the display unit for a channel value.
 *
 * Mirrors `chem_vault.domain.screening_assay.enums.unit_for_normalization`
 * on the backend so the FE can show the same suffix the channel resolver
 * stamps onto each CampaignMeasurement.unit at import time. Used to make
 * hit-threshold inputs explicit ("> 4 %") and to caption the comparison
 * with the right unit ("Hit if Raw Data > 4 %").
 *
 * Source-kind dispatch:
 *   - dose_response_curve → protocol's canonical dose_unit (uM/nM/etc.)
 *   - readout_data        → derived from the chosen normalization layer,
 *                           falling back to the readout's raw unit
 *
 * Normalization → unit mapping for readout_data (keep in lock-step with
 * the backend helper):
 *   percent_inhibition / percent_activation / percent_control → "%"
 *   z_score                                                   → unitless ("")
 *   null (raw layer) / unknown                                → raw_unit
 */
export function channelUnit(args: {
  sourceKind: "readout_data" | "dose_response_curve";
  rawUnit?: string | null;
  normalization?: string | null;
  doseUnit?: string | null;
}): string {
  const { sourceKind, rawUnit, normalization, doseUnit } = args;
  if (sourceKind === "dose_response_curve") {
    return doseUnit ?? "";
  }
  if (!normalization) return rawUnit ?? "";
  switch (normalization) {
    case "percent_inhibition":
    case "percent_activation":
    case "percent_control":
      return "%";
    case "z_score":
      return "";
    default:
      return rawUnit ?? "";
  }
}
