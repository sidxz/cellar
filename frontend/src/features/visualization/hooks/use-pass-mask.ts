"use client";

import { useMemo } from "react";
import { computePassMask } from "../lib/filters";
import { useWorkbench } from "../store/workbench-context";
import type { Dataset } from "../types";

/** 1 per row passing the workbench's filters; recomputed only when data or filters change. */
export function usePassMask(ds: Dataset): Uint8Array {
  const filters = useWorkbench((s) => s.filters);
  return useMemo(() => computePassMask(ds, filters), [ds, filters]);
}
