"use client";

import { useId } from "react";
import { newFilter } from "../../lib/filters";
import { useWorkbench } from "../../store/workbench-context";
import type { Dataset } from "../../types";
import { FieldSelect } from "../field-select";

/** "+ Add filter": any number or category field, grouped by readout → layer. The new
 * filter keeps every row until it is narrowed; a field already filtered is not added twice. */
export function AddFilterCombobox({ ds }: { ds: Dataset }) {
  const filters = useWorkbench((s) => s.filters);
  const upsertFilter = useWorkbench((s) => s.upsertFilter);
  const id = useId();
  const add = (key: string | undefined) => {
    if (!key || filters.some((f) => "key" in f && f.key === key)) return;
    const filter = newFilter(ds, key);
    if (filter) upsertFilter(filter);
  };
  return (
    <div>
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
      />
    </div>
  );
}
