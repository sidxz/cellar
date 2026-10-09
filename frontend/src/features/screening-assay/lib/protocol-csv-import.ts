import type {
  OntologyTerm,
  TermInUse,
} from "@/features/workspace-config/hooks/use-ontology-search";
import type { ProtocolForm } from "@/features/workspace-config/hooks/use-protocol-forms";
import type { ProtocolCategory } from "@/features/workspace-config/types";
import type { NamePreviewResponse } from "@/shared/lib/api/model";
import type { NamePreviewDraft } from "../hooks/use-protocol-name-preview";
import type { CreateProtocolInput, ProtocolReference, ProtocolType, Target } from "../types";
import { ontologyAnnotationsPayload } from "./ontology-annotations-payload";
import { conditionDefinitionsPayload, readoutDefinitionsPayload } from "./protocol-create-payload";
import {
  applyFormFacets,
  conditionsFromForm,
  formsForCategory,
  pickFormForCategory,
  readoutsFromForm,
} from "./protocol-form-apply";
import { normalizeReference } from "./protocol-references";

// ---------------------------------------------------------------------------
// File shape
// ---------------------------------------------------------------------------

export const PROTOCOL_CSV_COLUMNS = [
  "category",
  "organism",
  "strain",
  "cell_line",
  "target",
  "discriminator",
  "form",
  "nicknames",
  "references",
  "description",
] as const;

export type ProtocolCsvRow = Record<(typeof PROTOCOL_CSV_COLUMNS)[number], string>;

/** Headers plus a whole-cell example and a target-based one. Lists are `;`-separated. */
export function protocolCsvTemplate(): string {
  return [
    PROTOCOL_CSV_COLUMNS.join(","),
    "Growth inhibition,Mycobacterium tuberculosis,H37Rv,,,,MIC,MABA; Alamar blue MIC,doi:10.1000/example,Whole-cell MIC by resazurin reduction",
    "Enzyme inhibition,Escherichia coli,,,DHFR,,IC50 dose-response,,url:https://example.org/dhfr-assay,Purified enzyme IC50",
    "",
  ].join("\n");
}

/** Rows keyed by the template's columns (headers matched case-insensitively), or why the file can't be read. */
export function readProtocolCsv(parsed: {
  headers: string[];
  rows: Record<string, string>[];
}): { rows: ProtocolCsvRow[] } | { error: string } {
  const known = new Set<string>(PROTOCOL_CSV_COLUMNS);
  const columns = parsed.headers.map((h) => ({ raw: h, name: h.trim().toLowerCase() }));
  const unknown = columns.filter((c) => c.name && !known.has(c.name)).map((c) => c.raw.trim());
  if (!columns.some((c) => c.name === "category")) {
    return { error: "The file needs a category column." };
  }
  if (unknown.length > 0) {
    return { error: `Unknown column: ${unknown.join(", ")}. Use the template's columns.` };
  }
  const rows = parsed.rows.map((r) => {
    const out = Object.fromEntries(PROTOCOL_CSV_COLUMNS.map((c) => [c, ""])) as ProtocolCsvRow;
    for (const c of columns) {
      if (known.has(c.name)) out[c.name as keyof ProtocolCsvRow] = (r[c.raw] ?? "").trim();
    }
    return out;
  });
  return { rows };
}

const splitList = (s: string) =>
  s
    .split(";")
    .map((x) => x.trim())
    .filter(Boolean);

/** `kind:value` items, normalized the way the server stores them. */
function parseReferences(s: string): { references: ProtocolReference[]; errors: string[] } {
  const references: ProtocolReference[] = [];
  const errors: string[] = [];
  for (const item of splitList(s)) {
    const colon = item.indexOf(":");
    const kind = (colon < 0 ? item : item.slice(0, colon)).trim().toLowerCase();
    const result = normalizeReference(kind, colon < 0 ? "" : item.slice(colon + 1));
    if ("error" in result) errors.push(result.error);
    else references.push({ kind: kind as ProtocolReference["kind"], value: result.value });
  }
  return { references, errors };
}

// ---------------------------------------------------------------------------
// Resolution: nothing is ever guessed; anything not matched exactly waits for a pick
// ---------------------------------------------------------------------------

export type Resolution<T> =
  | { state: "empty" }
  | { state: "pending" }
  | { state: "resolved"; value: T }
  | { state: "unresolved"; query: string };

const same = (a: string | null | undefined, b: string) =>
  !!a && a.trim().toLowerCase() === b.trim().toLowerCase();

const one = <T>(matches: T[], query: string): Resolution<T> =>
  matches.length === 1 ? { state: "resolved", value: matches[0] } : { state: "unresolved", query };

/** Terms used here whose label or short label is the query. */
export function usedHereMatches(query: string, usedHere: TermInUse[]): TermInUse[] {
  return usedHere.filter((t) => same(t.label, query) || same(t.short_label, query));
}

/**
 * Organism or cell line: a term used here, else the exact lookup (a common name, or the one
 * ontology term whose label or synonym is the query). `exactHits` undefined means still looking.
 */
export function resolveTerm(
  query: string,
  usedHere: TermInUse[],
  exactHits: OntologyTerm[] | undefined,
): Resolution<OntologyTerm> {
  if (!query.trim()) return { state: "empty" };
  const here = usedHereMatches(query, usedHere);
  if (here.length === 1) {
    const { term_id, label, ontology_source, uri } = here[0];
    return { state: "resolved", value: { term_id, label, ontology_source, uri } };
  }
  if (!exactHits) return { state: "pending" };
  return one(exactHits, query);
}

/** By name among the category's forms (the generic ones when it has none); blank means its default. */
export function resolveForm(
  name: string,
  categoryId: string,
  forms: ProtocolForm[],
): Resolution<ProtocolForm> {
  if (!name.trim()) {
    const picked = pickFormForCategory(forms, categoryId);
    return picked ? { state: "resolved", value: picked } : { state: "unresolved", query: "" };
  }
  const { own, generic } = formsForCategory(forms, categoryId);
  return one(
    (own.length > 0 ? own : generic).filter((f) => same(f.name, name)),
    name,
  );
}

/** By registry name; when names repeat, by the row's organism too. */
export function resolveTarget(
  name: string,
  organisms: string[],
  targets: Target[],
): Resolution<Target> {
  const named = targets.filter((t) => same(t.name, name));
  if (named.length <= 1) return one(named, name);
  return one(
    named.filter((t) => organisms.some((o) => same(t.organism, o))),
    name,
  );
}

export interface ResolveContext {
  categories: ProtocolCategory[];
  forms: ProtocolForm[];
  targets: Target[];
  usedHere: { organism: TermInUse[]; cell_line: TermInUse[] };
  /** The exact lookup's terms for a slot's query; undefined while it runs. */
  exactHits: (slot: "organism" | "cell_line", query: string) => OntologyTerm[] | undefined;
}

/** What the chemist picked or typed in the preview, over the file's values. */
export interface RowPicks {
  category?: string;
  formId?: string;
  organism?: OntologyTerm;
  cell_line?: OntologyTerm;
  targetIds?: string[];
  discriminator?: string;
}

export interface ResolvedRow {
  csv: ProtocolCsvRow;
  category: Resolution<ProtocolCategory>;
  form: Resolution<ProtocolForm>;
  organism: Resolution<OntologyTerm>;
  cell_line: Resolution<OntologyTerm>;
  target: Resolution<string[]>;
  discriminator: string;
  nicknames: string[];
  references: ProtocolReference[];
  referenceErrors: string[];
  /** The facts the name is generated from; null until everything resolves. */
  draft: NamePreviewDraft | null;
}

const value = <T>(r: Resolution<T>): T | undefined =>
  r.state === "resolved" ? r.value : undefined;

export function resolveRow(csv: ProtocolCsvRow, ctx: ResolveContext, picks: RowPicks): ResolvedRow {
  const categoryLabel = picks.category ?? csv.category;
  const category: Resolution<ProtocolCategory> = picks.category
    ? one(
        ctx.categories.filter((c) => c.label === picks.category),
        picks.category,
      )
    : csv.category
      ? one(
          ctx.categories.filter((c) => same(c.label, csv.category)),
          csv.category,
        )
      : { state: "unresolved", query: categoryLabel };
  const cat = value(category);
  const pickedForm = picks.formId ? ctx.forms.find((f) => f.id === picks.formId) : undefined;
  const form: Resolution<ProtocolForm> = !cat
    ? { state: "empty" }
    : pickedForm
      ? { state: "resolved", value: pickedForm }
      : resolveForm(csv.form, cat.id, ctx.forms);
  const term = (slot: "organism" | "cell_line"): Resolution<OntologyTerm> => {
    const picked = picks[slot];
    if (picked) return { state: "resolved", value: picked };
    return resolveTerm(csv[slot], ctx.usedHere[slot], ctx.exactHits(slot, csv[slot].trim()));
  };
  const organism = term("organism");
  const cell_line = term("cell_line");
  const target: Resolution<string[]> = picks.targetIds?.length
    ? { state: "resolved", value: picks.targetIds }
    : !csv.target
      ? { state: "empty" }
      : (() => {
          const r = resolveTarget(
            csv.target,
            [csv.organism, value(organism)?.label ?? ""].filter(Boolean),
            ctx.targets,
          );
          return r.state === "resolved" ? { state: "resolved", value: [r.value.id] } : r;
        })();
  const discriminator = (picks.discriminator ?? csv.discriminator).trim();
  const { references, errors: referenceErrors } = parseReferences(csv.references);

  const f = value(form);
  const facts = [organism, cell_line, target];
  const ready = cat && f && facts.every((r) => r.state === "resolved" || r.state === "empty");
  const strain = csv.strain.trim();
  const draft: NamePreviewDraft | null = ready
    ? {
        category: cat.label,
        target_ids: value(target) ?? [],
        ontology_annotations: ontologyAnnotationsPayload({
          ...applyFormFacets({}, {}, f).annotations,
          organism: value(organism) ? [value(organism) as OntologyTerm] : [],
          cell_line: value(cell_line) ? [value(cell_line) as OntologyTerm] : [],
          strain: strain
            ? [
                {
                  term_id: `free_text:${strain}`,
                  label: strain,
                  ontology_source: "free_text",
                  uri: null,
                },
              ]
            : [],
        }),
        discriminator: discriminator || null,
        form_id: f.id,
      }
    : null;

  return {
    csv,
    category,
    form,
    organism,
    cell_line,
    target,
    discriminator,
    nicknames: splitList(csv.nicknames),
    references,
    referenceErrors,
    draft,
  };
}

/** Indices of rows whose generated name another row also gets → that other row's index. */
export function inFileClashes(names: (string | undefined)[]): Map<number, number> {
  const out = new Map<number, number>();
  names.forEach((name, i) => {
    if (!name) return;
    const j = names.findIndex((other, k) => k !== i && !!other && same(other, name));
    if (j >= 0) out.set(i, j);
  });
  return out;
}

const SLOT_WORDS = { organism: "the organism", cell_line: "the cell line", target: "the target" };

/** Why a row can't be created yet; empty when it can. `clashRow` is the file row it shares a name with. */
export function rowBlockers(
  r: ResolvedRow,
  preview: NamePreviewResponse | undefined,
  clashRow: number | null,
): string[] {
  const out: string[] = [];
  if (r.category.state !== "resolved") out.push("Pick a category");
  else if (r.form.state !== "resolved") out.push("Pick a form");
  for (const slot of ["organism", "cell_line", "target"] as const) {
    if (r[slot].state === "unresolved") out.push(`Pick ${SLOT_WORDS[slot]}`);
    if (r[slot].state === "pending") out.push(`Looking up ${SLOT_WORDS[slot]}…`);
  }
  out.push(...r.referenceErrors);
  if (!r.draft) return out;
  if (!preview) return [...out, "Generating the name…"];
  if (preview.missing_labels.length > 0) out.push(`Needs ${preview.missing_labels.join(", ")}`);
  if (preview.clash) out.push(`${preview.clash.code} already has this name: add a discriminator`);
  else if (preview.needs_discriminator) {
    out.push(
      `Shares its name with ${preview.siblings.map((s) => s.code).join(", ")}: add a discriminator`,
    );
  }
  if (preview.discriminator_error) out.push(preview.discriminator_error);
  if (clashRow !== null) out.push(`Same name as row ${clashRow} of this file: add a discriminator`);
  return out;
}

/** The POST /protocols body for a resolved row: the form's readouts and conditions, as the dialog sends them. */
export function rowCreatePayload(r: ResolvedRow): CreateProtocolInput {
  const form = value(r.form);
  if (!r.draft || !form) throw new Error("rowCreatePayload: the row is not resolved");
  const conditions = conditionDefinitionsPayload(conditionsFromForm(form));
  return {
    protocol_type: (form.protocol_type ?? "biochemical") as ProtocolType,
    discriminator: r.discriminator || null,
    target_ids: r.draft.target_ids ?? [],
    category: r.draft.category as string,
    description: r.csv.description || null,
    dose_unit: "uM",
    readout_definitions: readoutDefinitionsPayload(readoutsFromForm(form)),
    condition_definitions: conditions.length > 0 ? conditions : undefined,
    ontology_annotations: r.draft.ontology_annotations as Record<string, OntologyTerm[]>,
    form_id: form.id,
    nicknames: r.nicknames,
    references: r.references,
  };
}
