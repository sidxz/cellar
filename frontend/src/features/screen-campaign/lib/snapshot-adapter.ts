/**
 * Adapter: campaign `CurveSnapshot` → `DoseResponseCurve`
 *
 * The campaign grid's expand dialog renders via the same
 * `<DoseResponseChart isInteractive={false}>` that protocol-runs and
 * search use, so a closed-campaign curve looks bit-identical to its
 * protocol-tab counterpart. The chart consumes a `DoseResponseCurve`,
 * which is wider than the JSONB `curve_snapshot` we freeze on each
 * `CampaignMeasurement`.
 *
 * The wider fields (workspace_id, batch_id, run_id, …) are placeholders
 * here — the chart uses them only for query-key uniqueness and never
 * reads them.
 */

import type { CurveSnapshot } from "@/features/screening-assay/components/dose-response-figure";
import type {
  CurveClass,
  CurveType,
  DoseResponseCurve,
  InterceptValue,
} from "@/features/screening-assay/types";

const PLACEHOLDER_UUID = "00000000-0000-0000-0000-000000000000";

interface SnapshotAdapterContext {
  /** Reg number / display name for the chart header — chemists scan for
   *  this; falls back to the molecule_id slice when missing. */
  moleculeLabel: string;
  /** The channel's chemist-facing label (e.g. "Resazurin EC50") — fed to
   *  the chart's molecule_name slot so the SummaryCard header carries
   *  the same text the campaign chip shows. */
  channelLabel: string;
  /** Optional unit ("uM", "nM"). The chart's SummaryCard appends this to
   *  the headline value; pass null for unitless or unknown. */
  unit?: string | null;
}

export function snapshotToDoseResponseCurve(
  snap: CurveSnapshot,
  ctx: SnapshotAdapterContext,
): DoseResponseCurve {
  // The wide-shape `DoseResponseCurve` requires non-null FKs and
  // numeric fields the snapshot doesn't carry. Placeholders are safe —
  // the chart reads only the curve-shape + label fields. The snapshot
  // stores intercept_values as loose `Record<string, unknown>` (JSONB
  // round-trip); the chart's consumer expects the typed `InterceptValue`.
  // Two-step cast through `unknown` because tsc can't prove the shape
  // matches at the type level — the BE writes the same wire shape that
  // the InterceptValue type describes.
  const intercept_values = (snap.intercept_values ?? []) as unknown as InterceptValue[];

  return {
    id: PLACEHOLDER_UUID,
    workspace_id: PLACEHOLDER_UUID,
    molecule_id: PLACEHOLDER_UUID,
    registration_number: ctx.moleculeLabel,
    molecule_name: ctx.channelLabel,
    synonyms: [],
    smiles: null,
    batch_id: PLACEHOLDER_UUID,
    batch_number: null,
    protocol_id: PLACEHOLDER_UUID,
    run_id: PLACEHOLDER_UUID,
    readout_definition_id: PLACEHOLDER_UUID,
    // SummaryCard's legacy fallback path uses curve_type when
    // intercept_values is empty. Default to "ic50" — the same fallback
    // the chart's lib already does.
    curve_type: ((snap.curve_type as CurveType | null) ?? "ic50") as CurveType,
    fitted_value: snap.fitted_value,
    fitted_unit: ctx.unit ?? "",
    hill_slope: snap.hill_slope,
    top: snap.top,
    bottom: snap.bottom,
    r_squared: snap.r_squared ?? 0,
    confidence_interval_low: snap.confidence_interval_low ?? null,
    confidence_interval_high: snap.confidence_interval_high ?? null,
    num_points: Array.isArray(snap.raw_data) ? snap.raw_data.length : 0,
    curve_class: (snap.curve_class as CurveClass | null) ?? null,
    raw_data: (snap.raw_data ?? null) as Array<Record<string, unknown>> | null,
    excluded_points:
      (snap.excluded_points ?? null) as Array<Record<string, unknown>> | null,
    fit_quality_warnings: snap.fit_quality_warnings ?? [],
    intercept_values,
    // Aggregate-mode overlay carried through the snapshot so the expand
    // dialog's <DoseResponseChart> can draw the contributing curves muted
    // and place a single vertical marker at the cell's aggregate value
    // (rather than the rep curve's per-intercept dashed line, which
    // points at the latest run's intercept — not the aggregate).
    additional_curves:
      (snap.additional_curves ?? null) as Array<Record<string, unknown>> | null,
    aggregate: snap.aggregate ?? null,
  };
}
