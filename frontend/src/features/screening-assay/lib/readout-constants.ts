// Sentinel for the X-axis dropdown that means "use the well's concentration"
// (mapped to x_readout_name=null in the payload).
export const WELL_CONC_X = "__well_concentration__";

// FE-visible subset of the readout data-type enum. File / Date / Batch
// Link are dropped from the picker — they're either run-level metadata
// already modelled elsewhere (run.run_date, well.batch_id) or per-run
// attachments. The BE enum keeps them for legacy hydration.
export const VISIBLE_READOUT_DATA_TYPES: readonly string[] = [
  "numeric",
  "text",
  "pick_list",
  "dose_response",
] as const;

// Reserved readout-definition names that collide with built-in well metadata.
// Kept in sync with backend domain.screening_assay.protocol._RESERVED_READOUT_NAMES.
export const RESERVED_READOUT_NAMES: ReadonlySet<string> = new Set([
  "concentration",
  "dose",
  "well",
  "plate",
  "batch",
  "compound",
]);

export function isReservedReadoutName(name: string): boolean {
  return RESERVED_READOUT_NAMES.has(name.trim().toLowerCase());
}

// Default Top/Bottom/Hill fit ranges for percent-normalized readouts.
// Calibrated to match standard sigmoidal IC50 fits on percent inhibition /
// percent activation / percent control responses.
export const PERCENT_FIT_RANGES = {
  topMin: 85,
  topMax: 110,
  bottomMin: -10,
  bottomMax: 10,
  hillMin: 0.9,
  hillMax: 1.1,
} as const;

// Defaults for curve classification thresholds. Calibrated for percent
// readouts; raw-signal assays may override per-protocol.
export const CLASSIFICATION_THRESHOLD_DEFAULTS = {
  inactiveCutoff: 30,
  fullR2Min: 0.8,
  fullTopMin: 80,
  fullBottomMax: 20,
  partialR2Min: 0.6,
} as const;

// Default outlier rejection threshold (× SD of residuals) for dose-response
// fitting. Disabled by default; this is the value seeded when the feature
// is turned on.
export const DEFAULT_OUTLIER_SIGMA = 3;
