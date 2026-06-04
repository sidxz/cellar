import { groupBy } from "@/shared/lib/group-by";
import type { DoseResponseCurve, ReadoutData } from "../types";

export interface PivotRow {
  key: string;
  label: string;
  registrationNumber: string;
  moleculeName: string;
  /** molecule.name + custom synonyms, deduped against the registration number. */
  aliases: string[];
  batchNumber: string;
  /** Molecule SMILES for the optional structure column; null if unavailable. */
  smiles: string | null;
  moleculeId: string;
  batchId: string;
  /** null for well-less rows: engine aggregates merged onto wells, or
   * summary-import rows that have no plate/well at all (see step 4). */
  wellId: string | null;
  /** Keyed by `${readout_def_id}::${"raw"|"computed"}` so the raw and
   * post-normalization layers stay separate (they share readout_def_id).
   * Per-molecule calculated readouts are merged into every well row of the
   * same (molecule, batch) group. */
  values: Map<string, ReadoutData>;
  /** dose_response readout def id -> curve. Same value for every row in the
   * (molecule, batch) group — DR is not per-well. */
  curves: Map<string, DoseResponseCurve>;
}

export const valueKey = (defId: string, isComputed: boolean) =>
  `${defId}::${isComputed ? "c" : "r"}`;

/** Aliases for a row from its enriched name + synonyms, deduped against the
 * registration number so the Compound column doesn't echo Aliases. */
function buildAliases(row: ReadoutData): string[] {
  const aliases: string[] = [];
  if (
    row.molecule_name &&
    row.molecule_name !== row.registration_number &&
    !aliases.includes(row.molecule_name)
  ) {
    aliases.push(row.molecule_name);
  }
  for (const s of row.synonyms ?? []) {
    if (s && s !== row.registration_number && !aliases.includes(s)) {
      aliases.push(s);
    }
  }
  return aliases;
}

/** Pivot flat readout-data rows into compound-first table rows.
 *
 * `curveLookup` maps a dose_response readout-def id to a
 * `(molecule_id::batch_id) -> curve` map; it is read to attach the compound's
 * curve to every row of that (molecule, batch) group. */
export function pivotReadoutData(
  data: ReadoutData[] | undefined,
  curveLookup: Map<string, Map<string, DoseResponseCurve>>,
): PivotRow[] {
  if (!data) return [];

  // 1. Bucket per-molecule rows (no well_id) — these are calculated
  // readouts that the engine produced once per (mol, batch). They get
  // merged into every well row of the same group below.
  const perMolRows = data.filter((row) => row.molecule_id && !row.well_id);
  const perMol = groupBy(perMolRows, (row) => `${row.molecule_id}::${row.batch_id ?? ""}`);

  // 2. Group per-well rows by (molecule, batch, well). Track which
  // (molecule, batch) keys have at least one well so step 4 can tell which
  // well-less groups still need a row of their own.
  const groups = new Map<string, PivotRow>();
  const wellMolKeys = new Set<string>();
  for (const row of data) {
    if (!row.molecule_id) continue;
    if (!row.well_id) continue; // per-mol rows handled in steps 3-4
    const key = `${row.molecule_id}::${row.batch_id}::${row.well_id}`;
    let group = groups.get(key);
    if (!group) {
      const curveKey = `${row.molecule_id}::${row.batch_id ?? ""}`;
      const rowCurves = new Map<string, DoseResponseCurve>();
      for (const [defId, byKey] of curveLookup) {
        const c = byKey.get(curveKey);
        if (c) rowCurves.set(defId, c);
      }
      group = {
        key,
        label: row.registration_number ?? "Unknown",
        registrationNumber: row.registration_number ?? "",
        moleculeName: row.molecule_name ?? "",
        aliases: buildAliases(row),
        batchNumber: row.batch_number ?? "",
        smiles: row.smiles,
        moleculeId: row.molecule_id,
        batchId: row.batch_id ?? "",
        wellId: row.well_id,
        values: new Map(),
        curves: rowCurves,
      };
      groups.set(key, group);
      // Remember this (molecule, batch) has a well, so step 4 doesn't also
      // emit a standalone well-less row for it.
      wellMolKeys.add(`${row.molecule_id}::${row.batch_id ?? ""}`);
    }
    // Raw and computed layers share readout_definition_id but differ on
    // is_computed — key them separately so neither overwrites the other.
    group.values.set(valueKey(row.readout_definition_id, row.is_computed), row);
  }

  // 3. Merge per-(mol, batch) calculated readouts into every well of
  // that group so they show on every row that compound appears on.
  for (const group of groups.values()) {
    const molRows = perMol.get(`${group.moleculeId}::${group.batchId}`);
    if (!molRows) continue;
    for (const row of molRows) {
      group.values.set(valueKey(row.readout_definition_id, row.is_computed), row);
    }
  }

  // 4. Emit standalone rows for (molecule, batch) groups that have well-less
  // data but no well in this run — e.g. Summary Results Import into a run with
  // no plate data. Steps 2-3 only ever produce or augment well rows, so
  // without this these rows would never render.
  for (const [molKey, molRows] of perMol) {
    if (wellMolKeys.has(molKey)) continue;
    const first = molRows[0];
    if (!first.molecule_id) continue; // perMolRows are molecule-keyed; narrows type
    const curveKey = `${first.molecule_id}::${first.batch_id ?? ""}`;
    const rowCurves = new Map<string, DoseResponseCurve>();
    for (const [defId, byKey] of curveLookup) {
      const c = byKey.get(curveKey);
      if (c) rowCurves.set(defId, c);
    }
    const group: PivotRow = {
      key: `${molKey}::wellless`,
      label: first.registration_number ?? "Unknown",
      registrationNumber: first.registration_number ?? "",
      moleculeName: first.molecule_name ?? "",
      aliases: buildAliases(first),
      batchNumber: first.batch_number ?? "",
      smiles: first.smiles,
      moleculeId: first.molecule_id,
      batchId: first.batch_id ?? "",
      wellId: null,
      values: new Map(),
      curves: rowCurves,
    };
    for (const row of molRows) {
      group.values.set(valueKey(row.readout_definition_id, row.is_computed), row);
    }
    groups.set(group.key, group);
  }

  return Array.from(groups.values());
}
