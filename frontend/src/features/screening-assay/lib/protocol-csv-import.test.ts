import { parseCsvRows } from "@/shared/lib/parse-csv";
import { describe, expect, it } from "vitest";
import {
  PROTOCOL_CSV_COLUMNS,
  type ProtocolCsvRow,
  inFileClashes,
  protocolCsvTemplate,
  readProtocolCsv,
  resolveForm,
  resolveRow,
  resolveTarget,
  resolveTerm,
  rowBlockers,
  rowCreatePayload,
} from "./protocol-csv-import";

const MTB = {
  term_id: "http://purl.bioontology.org/ontology/NCBITAXON/1773",
  label: "Mycobacterium tuberculosis",
  ontology_source: "NCBITAXON",
  uri: "http://purl.bioontology.org/ontology/NCBITAXON/1773",
};
const MTB_IN_USE = { ...MTB, short_label: "M. tuberculosis", protocol_count: 3 };
const ECOLI = { ...MTB, term_id: "ecoli", label: "Escherichia coli", uri: null };

const row = (over: Partial<ProtocolCsvRow> = {}): ProtocolCsvRow => ({
  category: "",
  organism: "",
  strain: "",
  cell_line: "",
  target: "",
  discriminator: "",
  form: "",
  nicknames: "",
  references: "",
  description: "",
  ...over,
});

const CATEGORIES = [
  {
    id: "c-gi",
    workspace_id: "w",
    label: "Growth inhibition",
    name_pattern: "{organism} {strain?} growth inhibition",
    default_pattern: "",
    version: 1,
  },
  {
    id: "c-ei",
    workspace_id: "w",
    label: "Enzyme inhibition",
    name_pattern: "{target} inhibition",
    default_pattern: "",
    version: 1,
  },
];
const form = (id: string, name: string, category_id: string | null, is_default = false) => ({
  id,
  workspace_id: "w",
  name,
  category_id,
  is_default,
  protocol_type: "whole_cell",
  version: 1,
  readout_templates: [{ name: "MIC", data_type: "numeric", unit: "µM" }],
  condition_templates: [{ name: "Incubation", data_type: "numeric", unit: "h" }],
  ontology_defaults: [
    {
      slot_name: "assay_format",
      terms: [{ term_id: "bao:1", label: "organism-based", ontology_source: "BAO", uri: null }],
    },
  ],
});
const FORMS = [
  form("f-mic", "MIC", "c-gi", true),
  form("f-ic50", "IC50 dose-response", "c-gi"),
  form("f-ki", "Ki", "c-ei"),
  form("f-pct", "% inhibition", "c-ei"),
];
const target = (id: string, name: string, organism: string | null) => ({
  id,
  workspace_id: "w",
  name,
  target_type: "protein",
  organism,
});
const TARGETS = [
  target("t-inha", "InhA", "Mycobacterium tuberculosis"),
  target("t-dhfr-ec", "DHFR", "Escherichia coli"),
  target("t-dhfr-hs", "DHFR", "Homo sapiens"),
];

describe("template", () => {
  it("has the columns and a whole-cell and a target-based example row", () => {
    const lines = parseCsvRows(protocolCsvTemplate());
    expect(lines[0]).toEqual([...PROTOCOL_CSV_COLUMNS]);
    expect(lines).toHaveLength(3);
    const [, wholeCell, targetBased] = lines.map((l) =>
      Object.fromEntries(PROTOCOL_CSV_COLUMNS.map((c, i) => [c, l[i]])),
    );
    expect(wholeCell).toMatchObject({ category: "Growth inhibition", target: "" });
    expect(wholeCell.organism).not.toBe("");
    expect(wholeCell.strain).not.toBe("");
    expect(targetBased).toMatchObject({ category: "Enzyme inhibition" });
    expect(targetBased.target).not.toBe("");
    // Its lists and references parse as the importer reads them.
    const parsed = readProtocolCsv({ headers: lines[0], rows: [wholeCell, targetBased] });
    expect("rows" in parsed && parsed.rows).toHaveLength(2);
  });
});

describe("readProtocolCsv", () => {
  it("matches headers case-insensitively and fills absent columns", () => {
    const out = readProtocolCsv({ headers: [" Category "], rows: [{ " Category ": "Binding" }] });
    expect(out).toEqual({ rows: [row({ category: "Binding" })] });
  });
  it("refuses a file without a category column or with unknown columns", () => {
    expect(readProtocolCsv({ headers: ["organism"], rows: [] })).toEqual({
      error: "The file needs a category column.",
    });
    expect(readProtocolCsv({ headers: ["category", "organsim"], rows: [] })).toEqual({
      error: "Unknown column: organsim. Use the template's columns.",
    });
  });
});

describe("resolution order for organism and cell line", () => {
  it("takes a term used here before looking anything up", () => {
    expect(resolveTerm("m. tuberculosis", [MTB_IN_USE], undefined)).toEqual({
      state: "resolved",
      value: MTB,
    });
    expect(resolveTerm("Mycobacterium Tuberculosis", [MTB_IN_USE], [ECOLI])).toEqual({
      state: "resolved",
      value: MTB,
    });
  });
  it("then the exact lookup (common name or ontology exact match), only when it has one term", () => {
    expect(resolveTerm("Mtb", [], undefined)).toEqual({ state: "pending" });
    expect(resolveTerm("Mtb", [], [MTB])).toEqual({ state: "resolved", value: MTB });
    expect(resolveTerm("Myco", [], [MTB, ECOLI])).toEqual({ state: "unresolved", query: "Myco" });
    expect(resolveTerm("zzz", [], [])).toEqual({ state: "unresolved", query: "zzz" });
  });
  it("is empty for a blank cell", () => {
    expect(resolveTerm("  ", [MTB_IN_USE], undefined)).toEqual({ state: "empty" });
  });
});

describe("form and target", () => {
  it("finds a form by name in the category; blank means its default", () => {
    expect(resolveForm("ic50 DOSE-response", "c-gi", FORMS)).toMatchObject({
      state: "resolved",
      value: { id: "f-ic50" },
    });
    expect(resolveForm("", "c-gi", FORMS)).toMatchObject({ value: { id: "f-mic" } });
    expect(resolveForm("Ki", "c-gi", FORMS)).toEqual({ state: "unresolved", query: "Ki" });
    // Two forms and no default: the chemist picks one.
    expect(resolveForm("", "c-ei", FORMS)).toEqual({ state: "unresolved", query: "" });
  });
  it("finds a target by name, with the organism when names repeat", () => {
    expect(resolveTarget("inha", [], TARGETS)).toMatchObject({ value: { id: "t-inha" } });
    expect(resolveTarget("DHFR", [], TARGETS)).toEqual({ state: "unresolved", query: "DHFR" });
    expect(resolveTarget("DHFR", ["Escherichia coli"], TARGETS)).toMatchObject({
      value: { id: "t-dhfr-ec" },
    });
    expect(resolveTarget("KatG", ["Escherichia coli"], TARGETS)).toEqual({
      state: "unresolved",
      query: "KatG",
    });
  });
});

const ctx = (exact: Record<string, unknown[]> = {}) => ({
  categories: CATEGORIES,
  forms: FORMS,
  targets: TARGETS,
  usedHere: { organism: [MTB_IN_USE], cell_line: [] },
  exactHits: (slot: string, q: string) => exact[`${slot}|${q}`] as (typeof MTB)[] | undefined,
});

describe("resolveRow and blockers", () => {
  it("resolves a whole-cell row and builds its preview draft and create payload", () => {
    const r = resolveRow(
      row({
        category: "growth inhibition",
        organism: "Mtb",
        strain: "H37Rv",
        nicknames: "MABA; resazurin MIC",
        references: "doi:10.1128/AAC.1-23; pmid:19919034",
        description: "Resazurin reduction",
      }),
      ctx({ "organism|Mtb": [MTB] }),
      {},
    );
    expect(rowBlockers(r, undefined, null)).toEqual(["Generating the name…"]);
    expect(r.draft).toEqual({
      category: "Growth inhibition",
      target_ids: [],
      ontology_annotations: {
        assay_format: FORMS[0].ontology_defaults[0].terms,
        organism: [MTB],
        strain: [
          { term_id: "free_text:H37Rv", label: "H37Rv", ontology_source: "free_text", uri: null },
        ],
      },
      discriminator: null,
      form_id: "f-mic",
    });
    const payload = rowCreatePayload(r);
    expect(payload).toMatchObject({
      protocol_type: "whole_cell",
      category: "Growth inhibition",
      discriminator: null,
      form_id: "f-mic",
      description: "Resazurin reduction",
      nicknames: ["MABA", "resazurin MIC"],
      references: [
        { kind: "doi", value: "10.1128/AAC.1-23" },
        { kind: "pmid", value: "19919034" },
      ],
      ontology_annotations: r.draft?.ontology_annotations,
      readout_definitions: [expect.objectContaining({ name: "MIC", unit: "µM" })],
      condition_definitions: [{ name: "Incubation", data_type: "numeric", unit: "h" }],
    });
  });

  it("blocks unresolved, pending and bad-reference rows; a pick resolves them", () => {
    const r = resolveRow(
      row({ category: "Nope", organism: "Myco", references: "isbn:123; doi:nope" }),
      ctx({ "organism|Myco": [MTB, ECOLI] }),
      {},
    );
    expect(r.draft).toBeNull();
    expect(rowBlockers(r, undefined, null)).toEqual([
      "Pick a category",
      "Pick the organism",
      'Unknown reference kind "isbn"',
      "Not a valid DOI",
    ]);
    const picked = resolveRow(
      row({ category: "Nope", organism: "Myco" }),
      ctx({ "organism|Myco": [MTB, ECOLI] }),
      { category: "Growth inhibition", organism: ECOLI },
    );
    expect(picked.draft?.ontology_annotations?.organism).toEqual([ECOLI]);
    expect(
      rowBlockers(
        resolveRow(row({ category: "Growth inhibition", organism: "x" }), ctx(), {}),
        undefined,
        null,
      ),
    ).toEqual(["Looking up the organism…"]);
  });

  it("flags a clash with an existing protocol and with another row", () => {
    const r = resolveRow(
      row({ category: "Growth inhibition", organism: "Mtb" }),
      ctx({ "organism|Mtb": [MTB] }),
      {},
    );
    const preview = {
      name: "M. tuberculosis growth inhibition",
      base: "M. tuberculosis growth inhibition",
      missing: [],
      missing_labels: [],
      clash: {
        protocol_id: "p7",
        code: "PRT-0007",
        name: "M. tuberculosis growth inhibition",
        discriminator: null,
        status: "active",
        is_locked: false,
      },
      siblings: [],
      needs_discriminator: false,
      discriminator_error: null,
      discriminator_in_pattern: false,
      sibling_renames: [],
    };
    expect(rowBlockers(r, preview, null)).toEqual([
      "PRT-0007 already has this name: add a discriminator",
    ]);
    expect(rowBlockers(r, { ...preview, clash: null }, 3)).toEqual([
      "Same name as row 3 of this file: add a discriminator",
    ]);
    expect(rowBlockers(r, { ...preview, clash: null }, null)).toEqual([]);
  });

  it("asks for a blank fact the pattern needs, and only then", () => {
    const blank = resolveRow(row({ category: "Growth inhibition" }), ctx(), {});
    expect(blank.organism).toEqual({ state: "unresolved", query: "" });
    // {strain?} is optional: blank stays blank.
    expect(blank.strain).toEqual({ state: "empty" });
    expect(blank.draft).toBeNull();
    expect(rowBlockers(blank, undefined, null)).toEqual(["Pick the organism"]);

    const strainNeeded = {
      ...ctx(),
      categories: [{ ...CATEGORIES[0], name_pattern: "{organism} {strain} growth inhibition" }],
    };
    const r = resolveRow(row({ category: "Growth inhibition", organism: "Mtb" }), strainNeeded, {
      organism: MTB,
    });
    expect(r.strain).toEqual({ state: "unresolved", query: "" });
    expect(rowBlockers(r, undefined, null)).toEqual(["Pick the strain"]);
    const STRAIN = {
      term_id: "free_text:Erdman",
      label: "Erdman",
      ontology_source: "free_text",
      uri: null,
    };
    const picked = resolveRow(row({ category: "Growth inhibition" }), strainNeeded, {
      organism: MTB,
      strain: STRAIN,
    });
    expect(picked.draft?.ontology_annotations).toMatchObject({ organism: [MTB], strain: [STRAIN] });

    // A target-based pattern asks for the target, not the organism.
    const target = resolveRow(row({ category: "Enzyme inhibition", form: "Ki" }), ctx(), {});
    expect(target.target).toEqual({ state: "unresolved", query: "" });
    expect(target.organism).toEqual({ state: "empty" });
  });

  it("finds rows that would get the same name", () => {
    expect(inFileClashes(["A", "B", undefined, "a", "C", undefined])).toEqual(
      new Map([
        [0, 3],
        [3, 0],
      ]),
    );
  });
});
