"use client";

import {
  ColumnMappingTable,
  type MappingRow,
} from "@/features/chemical-registration/components/column-mapping-table";
import { useSuggestColumnMapping } from "@/features/chemical-registration/hooks/use-registration-wizard-api";
import {
  TARGET_GROUPS,
  oneColumnPerTarget,
} from "@/features/chemical-registration/lib/column-targets";
import { Button } from "@/shared/components/ui/button";
import type {
  ColumnMappingBody,
  ColumnMappingColumnBody,
  VaultFieldsResponse,
} from "@/shared/lib/api/model";
import { useEffect, useMemo, useState } from "react";
import { useUpdateDataSource, useVaultFields } from "../hooks/use-data-sources";

const GROUP_TITLES = { Compound: "Molecule fields", Batch: "Batch fields" } as const;

interface Props {
  dataSourceId: string;
  saved: ColumnMappingColumnBody[] | null | undefined;
}

const groupOf = (header: string) => (header.startsWith("batch.") ? "Batch" : "Compound");

/**
 * One row per vault field, keyed by the saved header that reads it when there is one (a
 * built-in such as "name" sits in "name|cdd_registry_number"), so a Save gives back every
 * saved column as it was. Saved columns no vault field names get a row of their own.
 */
function buildRows(
  fields: VaultFieldsResponse | undefined,
  saved: ColumnMappingColumnBody[],
): { rows: MappingRow[]; savedBy: Map<string, ColumnMappingColumnBody> } {
  const savedBy = new Map(saved.map((c) => [c.header, c]));
  const claimed = new Set<string>();
  const rows: MappingRow[] = [];
  const vault = fields
    ? [
        ...fields.molecule.map((f) => ({ ...f, group: "Compound" as const })),
        ...fields.batch.map((f) => ({ ...f, group: "Batch" as const })),
      ]
    : [];
  for (const f of vault) {
    const header = savedBy.has(f.path)
      ? f.path
      : saved.find((c) => c.header.split("|").some((p) => p.trim() === f.path))?.header;
    if (header && claimed.has(header)) continue; // read by an earlier row's header
    if (header) claimed.add(header);
    rows.push({ key: header ?? f.path, label: f.label, group: f.group });
  }
  for (const c of saved) {
    if (claimed.has(c.header)) continue;
    rows.push({ key: c.header, label: c.header, group: groupOf(c.header) });
  }
  // Group titles show where the group changes: molecule rows first.
  rows.sort((a, b) => Number(a.group === "Batch") - Number(b.group === "Batch"));
  return { rows, savedBy };
}

/**
 * "Match fields": where each field of the vault goes. A saved entry always wins; fields it
 * does not mention start from the server's suggestion for their label (else "Don't import").
 */
export function MatchFields({ dataSourceId, saved }: Props) {
  const { data: fields, error } = useVaultFields(dataSourceId);
  const suggest = useSuggestColumnMapping();
  const update = useUpdateDataSource(dataSourceId);
  const [mapping, setMapping] = useState<ColumnMappingBody | null>(null);

  const { rows, savedBy } = useMemo(() => buildRows(fields, saved ?? []), [fields, saved]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: build once per fields/saved load; the mutation is stable.
  useEffect(() => {
    if (!fields && !error) return;
    const build = (byLabel: Map<string, ColumnMappingColumnBody>) => {
      const columns = rows.map((r): ColumnMappingColumnBody => {
        const s = savedBy.get(r.key);
        if (s) return s;
        const g = byLabel.get(r.label);
        // A suggestion only counts when it is a target of this field's level.
        const ok =
          g && TARGET_GROUPS.some((t) => t.label === r.group && t.targets.includes(g.target));
        return ok
          ? { header: r.key, target: g.target, source: g.source ?? null, separator: g.separator }
          : { header: r.key, target: "ignore", source: null };
      });
      // A saved field keeps its target; a suggestion for one already taken is dropped.
      setMapping({ columns: oneColumnPerTarget(columns, (c) => savedBy.has(c.header)) });
    };
    const unsaved = rows.filter((r) => !savedBy.has(r.key)).map((r) => r.label);
    if (unsaved.length === 0) return build(new Map());
    suggest
      .mutateAsync(unsaved)
      .then((m) => build(new Map(m.columns.map((c) => [c.header, c]))))
      .catch(() => build(new Map()));
  }, [rows, savedBy, error]);

  if (!mapping) return <p className="text-sm text-muted-foreground">Reading the vault's fields…</p>;

  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-base font-semibold">Match fields</h3>
        <p className="text-sm text-muted-foreground">
          Each field of the vault goes to one place in ChemCellar. Fields set to Don't import are
          left behind.
        </p>
        {error && (
          <p className="mt-1 text-sm text-destructive">
            Couldn't read the vault's fields: {error.message}
          </p>
        )}
      </div>
      <div className="max-h-[520px] overflow-auto rounded-md border">
        <ColumnMappingTable
          rows={rows}
          mapping={mapping}
          onChange={setMapping}
          rowHeading="Vault field"
          groupTitles={GROUP_TITLES}
        />
      </div>
      <Button
        type="button"
        disabled={update.isPending}
        onClick={() => update.mutate({ registration_mapping: mapping.columns })}
      >
        {update.isPending ? "Saving..." : "Save field matching"}
      </Button>
    </div>
  );
}
