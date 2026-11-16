/** Row cap for one dataset; mirrors MAX_DATASET_ROWS on the backend. */
export const MAX_ROWS = 100_000;

/** Most R groups an R-group matrix axis shows (most-populated first); mirrors the SAR
 * heatmap's server cap. */
export const MATRIX_AXIS_CAP = 30;

/** Compounds the cluster job accepts; mirrors the UMAP cluster route's bounds. */
export const CLUSTER_MIN_COMPOUNDS = 10;
export const CLUSTER_MAX_COMPOUNDS = 50_000;
