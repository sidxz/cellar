import { describe, expect, it } from "vitest";
import type { ProtocolReference } from "../types";
import {
  normalizeReference,
  paperLevelReferences,
  referenceHref,
  referenceKey,
} from "./protocol-references";

describe("normalizeReference (mirrors the backend VO)", () => {
  it.each([
    ["chembl_assay", "CHEMBL1054500", "CHEMBL1054500"],
    ["pubchem_aid", "AID 1851", "1851"],
    ["pubchem_aid", "aid1851", "1851"],
    ["doi", "https://doi.org/10.1021/JM901137J", "10.1021/JM901137J"],
    ["doi", "http://doi.org/10.1021/jm901137j", "10.1021/jm901137j"],
    ["doi", "doi:10.1021/jm901137j", "10.1021/jm901137j"],
    ["pmid", " 19919034 ", "19919034"],
    ["url", "https://example.org/a?b=1", "https://example.org/a?b=1"],
  ] as const)("%s %s → %s", (kind, raw, value) => {
    expect(normalizeReference(kind, raw)).toEqual({ value });
  });

  it.each([
    ["url", "javascript:alert(1)"],
    ["url", "data:text/html,x"],
    ["url", "https://"],
    ["chembl_assay", "1054500"],
    ["pubchem_aid", "AID"],
    ["doi", "10.12/x"],
    ["pmid", "PMID1"],
    ["pmid", ""],
  ] as const)("refuses %s %s", (kind, raw) => {
    expect(normalizeReference(kind, raw)).toHaveProperty("error");
  });
});

describe("referenceHref", () => {
  it.each([
    [
      { kind: "chembl_assay", value: "CHEMBL1054500" },
      "https://www.ebi.ac.uk/chembl/explore/assay/CHEMBL1054500",
    ],
    [{ kind: "pubchem_aid", value: "1851" }, "https://pubchem.ncbi.nlm.nih.gov/bioassay/1851"],
    [{ kind: "doi", value: "10.1021/jm901137j" }, "https://doi.org/10.1021/jm901137j"],
    [{ kind: "pmid", value: "19919034" }, "https://pubmed.ncbi.nlm.nih.gov/19919034"],
    [{ kind: "url", value: "https://example.org/x" }, "https://example.org/x"],
  ] as [ProtocolReference, string][])("%o → %s", (ref, href) => {
    expect(referenceHref(ref)).toBe(href);
  });

  it("never links a value that fails validation", () => {
    expect(referenceHref({ kind: "url", value: "javascript:alert(1)" })).toBeNull();
    expect(referenceHref({ kind: "pmid", value: "1/../../evil" })).toBeNull();
  });
});

describe("helpers", () => {
  const refs: ProtocolReference[] = [
    { kind: "chembl_assay", value: "CHEMBL1054500" },
    { kind: "pubchem_aid", value: "1851" },
    { kind: "doi", value: "10.1021/jm901137j" },
    { kind: "pmid", value: "19919034" },
    { kind: "url", value: "https://example.org" },
  ];

  it("keeps only paper-level references (DOI, PMID, URL)", () => {
    expect(paperLevelReferences(refs).map((r) => r.kind)).toEqual(["doi", "pmid", "url"]);
  });

  it("keys a reference as kind:value", () => {
    expect(referenceKey(refs[2])).toBe("doi:10.1021/jm901137j");
  });
});
