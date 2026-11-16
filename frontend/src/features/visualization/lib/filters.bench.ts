import { bench, describe } from "vitest";
import type { Dataset, DatasetColumn } from "../types";
import { type Filter, binCounts, computePassMask, fixedBins } from "./filters";

// Run: pnpm vitest bench --run src/features/visualization/lib/filters.bench.ts

const N_COLUMNS = 40; // 30 numeric + 10 category
const WELL_TYPES = ["sample", "negative_control", "positive_control"];

function syntheticDataset(rows: number): Dataset {
  const columns: DatasetColumn[] = [];
  const values: Record<string, unknown[]> = {};
  for (let c = 0; c < N_COLUMNS; c++) {
    const numeric = c < 30;
    const key = numeric ? `n${c}` : `c${c}`;
    columns.push({ key, label: key, kind: numeric ? "number" : "category", provenance: {} });
    values[key] = Array.from({ length: rows }, (_, i) => {
      if (i % 50 === c) return null; // ~2 % missing
      return numeric ? ((i * 7919 + c * 104729) % 10007) / 100 : WELL_TYPES[(i + c) % 3];
    });
  }
  return {
    revision: "bench",
    level: "wells",
    row_count: rows,
    row_ids: Array.from({ length: rows }, (_, i) => `r${i}`),
    columns,
    values,
  };
}

const FILTERS: Filter[] = [
  { id: "a", kind: "range", key: "n0", min: 10, max: 90, includeMissing: false },
  { id: "b", kind: "range", key: "n1", min: 5, max: null, includeMissing: true },
  { id: "c", kind: "range", key: "n2", min: null, max: 95, includeMissing: false },
  {
    id: "d",
    kind: "category",
    key: "c30",
    values: ["sample", "negative_control"],
    includeMissing: false,
  },
];

for (const rows of [50_000, 100_000, 200_000]) {
  const ds = syntheticDataset(rows);
  const mask = computePassMask(ds, FILTERS);
  const { edges } = fixedBins(ds, "n3");
  describe(`${rows.toLocaleString("en-US")} rows × ${N_COLUMNS} columns`, () => {
    bench("computePassMask, 4 filters", () => {
      computePassMask(ds, FILTERS);
    });
    bench("binCounts, 30 bins", () => {
      binCounts(ds, "n3", edges, mask);
    });
  });
}
