"use client";

import type { ProtocolForm } from "@/features/workspace-config/hooks/use-protocol-forms";
import type { ProtocolCategory } from "@/features/workspace-config/types";
import { OntologySearchInput } from "@/shared/components/ontology-search-input";
import { Input } from "@/shared/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { TableCell, TableRow } from "@/shared/components/ui/table";
import type { NamePreviewResponse } from "@/shared/lib/api/model";
import { CheckCircle2 } from "lucide-react";
import type { ProtocolFacetSlot } from "../../hooks/use-protocol-facet-slots";
import type { ResolvedRow, RowPicks } from "../../lib/protocol-csv-import";
import { formsForCategory } from "../../lib/protocol-form-apply";
import type { Target } from "../../types";
import { facetPlaceholder } from "../create-protocol/required-facts";
import { TargetMultiSelect } from "../target-multi-select";

const FACT_LABELS = { organism: "Organism", strain: "Strain", cell_line: "Cell line" };

/** One file row: what resolved reads as text; what didn't gets a picker in place. */
export function ImportRow({
  line,
  row,
  preview,
  blockers,
  error,
  categories,
  forms,
  targets,
  facetSlots,
  onPick,
}: {
  /** The file line, as the chemist sees it in a spreadsheet (header is line 1). */
  line: number;
  row: ResolvedRow;
  preview?: NamePreviewResponse;
  blockers: string[];
  error: string | null;
  categories: ProtocolCategory[];
  forms: ProtocolForm[];
  targets: Target[];
  facetSlots: ProtocolFacetSlot[];
  onPick: (picks: RowPicks) => void;
}) {
  const term = (slot: "organism" | "cell_line" | "strain") => {
    const r = row[slot];
    if (r.state === "resolved") return r.value.label;
    if (r.state !== "unresolved") return r.state === "pending" ? row.csv[slot] : "";
    const def = facetSlots.find((s) => s.name === slot);
    return (
      def && (
        <div className="grid gap-1">
          <span className="text-xs text-muted-foreground">
            {r.query ? `"${r.query}" not found` : "The name needs it"}
          </span>
          <OntologySearchInput
            ontologySources={def.ontology_sources}
            rootConceptId={def.root_concept_id}
            slot={slot}
            value={[]}
            onChange={(terms) => onPick({ [slot]: terms.at(-1) })}
            allowFreeText={def.allow_free_text}
            placeholder={facetPlaceholder(def)}
          />
        </div>
      )
    );
  };

  const category =
    row.category.state === "resolved" ? (
      row.category.value.label
    ) : (
      <Select onValueChange={(label) => onPick({ category: label, formId: undefined })}>
        <SelectTrigger aria-label="Category" className="h-8">
          <SelectValue placeholder={row.csv.category || "Pick a category"} />
        </SelectTrigger>
        <SelectContent>
          {categories.map((c) => (
            <SelectItem key={c.id} value={c.label}>
              {c.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );

  const categoryId = row.category.state === "resolved" ? row.category.value.id : null;
  const { own, generic } = formsForCategory(forms, categoryId);
  const form =
    row.form.state === "resolved" ? (
      row.form.value.name
    ) : row.form.state === "unresolved" ? (
      <Select onValueChange={(formId) => onPick({ formId })}>
        <SelectTrigger aria-label="Form" className="h-8">
          <SelectValue placeholder={row.csv.form || "Pick a form"} />
        </SelectTrigger>
        <SelectContent>
          {(own.length > 0 ? own : generic).map((f) => (
            <SelectItem key={f.id} value={f.id}>
              {f.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    ) : null;

  const target =
    row.target.state === "resolved" ? (
      row.target.value.map((id) => targets.find((t) => t.id === id)?.name ?? id).join(", ")
    ) : row.target.state === "unresolved" ? (
      <div className="grid gap-1">
        <span className="text-xs text-muted-foreground">
          {row.target.query ? `"${row.target.query}" not found or ambiguous` : "The name needs it"}
        </span>
        <TargetMultiSelect value={[]} onChange={(targetIds) => onPick({ targetIds })} />
      </div>
    ) : null;

  return (
    <TableRow data-testid={`csv-row-${line}`} className="align-top">
      <TableCell className="text-muted-foreground">{line}</TableCell>
      <TableCell className="min-w-48 font-medium">
        {preview?.name ?? <span className="text-muted-foreground">—</span>}
      </TableCell>
      <TableCell className="min-w-40">{category}</TableCell>
      <TableCell className="min-w-36">{form}</TableCell>
      <TableCell className="min-w-56">
        <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 text-sm">
          {(["organism", "strain", "cell_line"] as const).map(
            (slot) =>
              row[slot].state !== "empty" && (
                <FactRow key={slot} label={FACT_LABELS[slot]}>
                  {term(slot)}
                </FactRow>
              ),
          )}
          {target && <FactRow label="Target">{target}</FactRow>}
        </dl>
      </TableCell>
      <TableCell className="min-w-36">
        <Input
          aria-label="Discriminator"
          className="h-8"
          defaultValue={row.discriminator}
          placeholder="Only if needed"
          onBlur={(e) => {
            if (e.target.value.trim() !== row.discriminator)
              onPick({ discriminator: e.target.value });
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") e.currentTarget.blur();
          }}
        />
      </TableCell>
      <TableCell className="min-w-56 text-sm">
        {error && <p className="text-destructive">{error}</p>}
        {blockers.length === 0 ? (
          <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400">
            <CheckCircle2 className="h-4 w-4" aria-hidden />
            Ready
          </span>
        ) : (
          <ul className="space-y-0.5 text-amber-700 dark:text-amber-400">
            {blockers.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        )}
      </TableCell>
    </TableRow>
  );
}

function FactRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      <dd>{children}</dd>
    </>
  );
}
