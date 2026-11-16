"use client";

import { SearchableSelect } from "@/shared/components/searchable-select";
import type { Dataset, DatasetColumn } from "../types";

/** A searchable picker of the dataset's visible columns of ``kinds``, grouped by readout
 * (each readout's layers under it; conditions and well details in their own groups). */
export function FieldSelect({
  ds,
  kinds,
  value,
  onChange,
  id,
  clearable = false,
  placeholder = "None",
  disabledReason,
}: {
  ds: Dataset;
  kinds: DatasetColumn["kind"][];
  value: string | undefined;
  onChange: (key: string | undefined) => void;
  id?: string;
  /** Offer "None" (for optional settings such as color or split). */
  clearable?: boolean;
  placeholder?: string;
  /** Why a field cannot be chosen here, if it cannot (it stays listed, disabled). */
  disabledReason?: (c: DatasetColumn) => string | undefined;
}) {
  const options = ds.columns
    .filter((c) => !c.hidden && kinds.includes(c.kind))
    .map((c) => ({
      value: c.key,
      label: c.label,
      group: c.group ?? "Details",
      disabledReason: disabledReason?.(c),
    }));
  return (
    <SearchableSelect
      id={id}
      options={options}
      value={value ?? null}
      onValueChange={(key) => onChange(key ?? undefined)}
      clearable={clearable}
      placeholder={placeholder}
      searchPlaceholder="Search fields…"
      emptyMessage="No matching field."
      className="h-8 min-w-0 px-2 text-sm"
    />
  );
}
