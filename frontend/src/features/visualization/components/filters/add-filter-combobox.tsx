"use client";

import { useId, useMemo, useState } from "react";
import { datasetMoleculeIds } from "../../lib/dataset";
import { newFilter } from "../../lib/filters";
import { useWorkbench } from "../../store/workbench-context";
import type { Dataset } from "../../types";
import { FieldSelect } from "../field-select";
import { SubstructureQuery } from "./substructure-filter-card";

const SUBSTRUCTURE = "\u0000substructure";

/** "+ Add filter": "Substructure…" (draw a query, matched against the dataset's compounds),
 * then any number or category field, grouped by readout → layer. A field filter keeps every
 * row until it is narrowed; a field already filtered is not added twice. */
export function AddFilterCombobox({ ds }: { ds: Dataset }) {
  const filters = useWorkbench((s) => s.filters);
  const upsertFilter = useWorkbench((s) => s.upsertFilter);
  // null until the chemist first asks for a substructure: nothing to mount before that.
  const [drawing, setDrawing] = useState<boolean | null>(null);
  const hasCompounds = useMemo(() => datasetMoleculeIds(ds).length > 0, [ds]);
  const id = useId();
  const add = (key: string | undefined) => {
    if (key === SUBSTRUCTURE) {
      setDrawing(true);
      return;
    }
    if (!key || filters.some((f) => "key" in f && f.key === key)) return;
    const filter = newFilter(ds, key);
    if (filter) upsertFilter(filter);
  };
  return (
    <div className="space-y-2">
      <label htmlFor={id} className="sr-only">
        Add filter
      </label>
      <FieldSelect
        id={id}
        ds={ds}
        kinds={["number", "category"]}
        value={undefined}
        onChange={add}
        placeholder="+ Add filter: search fields…"
        leading={[
          {
            value: SUBSTRUCTURE,
            label: "Substructure…",
            disabledReason: hasCompounds ? undefined : "No compounds in this dataset",
          },
        ]}
      />
      {drawing !== null && <SubstructureQuery ds={ds} open={drawing} onOpenChange={setDrawing} />}
    </div>
  );
}
