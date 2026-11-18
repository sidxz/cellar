"use client";

import { ColumnMappingTable } from "@/features/chemical-registration/components/column-mapping-table";
import { useSuggestColumnMapping } from "@/features/chemical-registration/hooks/use-registration-wizard-api";
import { TARGET_GROUPS } from "@/features/chemical-registration/lib/column-targets";
import { Button } from "@/shared/components/ui/button";
import type { ColumnMappingBody, ColumnMappingColumnBody } from "@/shared/lib/api/model";
import { useEffect, useMemo, useState } from "react";
import { useUpdateDataSource, useVaultFields } from "../hooks/use-data-sources";

const GROUP_TITLES = { Compound: "Molecule fields", Batch: "Batch fields" } as const;

interface Props {
  dataSourceId: string;
  saved: ColumnMappingColumnBody[] | null | undefined;
}

/**
 * "Match fields": where each field of the vault goes. A saved entry always wins; fields it
 * does not mention start from the server's suggestion for their label (else "Don't import").
 */
export function MatchFields({ dataSourceId, saved }: Props) {
  const { data: fields } = useVaultFields(dataSourceId);
  const suggest = useSuggestColumnMapping();
  const update = useUpdateDataSource(dataSourceId);
  const [mapping, setMapping] = useState<ColumnMappingBody | null>(null);

  const rows = useMemo(
    () =>
      fields
        ? [
            ...fields.molecule.map((f) => ({
              key: f.path,
              label: f.label,
              group: "Compound" as const,
            })),
            ...fields.batch.map((f) => ({ key: f.path, label: f.label, group: "Batch" as const })),
          ]
        : [],
    [fields],
  );

  // biome-ignore lint/correctness/useExhaustiveDependencies: build once per fields/saved load; the mutation is stable.
  useEffect(() => {
    if (!fields) return;
    const savedBy = new Map((saved ?? []).map((c) => [c.header, c]));
    const build = (byLabel: Map<string, ColumnMappingColumnBody>) =>
      setMapping({
        columns: rows.map((r) => {
          const s = savedBy.get(r.key);
          if (s) return { ...s, header: r.key };
          const g = byLabel.get(r.label);
          // A suggestion only counts when it is a target of this field's level.
          const ok =
            g && TARGET_GROUPS.some((t) => t.label === r.group && t.targets.includes(g.target));
          return ok
            ? { header: r.key, target: g.target, source: g.source ?? null, separator: g.separator }
            : { header: r.key, target: "ignore", source: null };
        }),
      });
    const unsaved = rows.filter((r) => !savedBy.has(r.key)).map((r) => r.label);
    if (unsaved.length === 0) return build(new Map());
    suggest
      .mutateAsync(unsaved)
      .then((m) => build(new Map(m.columns.map((c) => [c.header, c]))))
      .catch(() => build(new Map()));
  }, [fields, saved]);

  if (!mapping) return <p className="text-sm text-muted-foreground">Reading the vault's fields…</p>;

  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-base font-semibold">Match fields</h3>
        <p className="text-sm text-muted-foreground">
          Each field of the vault goes to one place in ChemCellar. Fields set to Don't import are
          left behind.
        </p>
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
