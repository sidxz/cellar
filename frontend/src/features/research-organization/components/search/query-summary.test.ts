import type { Protocol } from "@/features/screening-assay/types";
import { describe, expect, it } from "vitest";
import type { SearchQuery } from "../../types";
import { querySummaryText, searchQueryKey } from "./query-summary";

const assay = (id: string) => ({ type: "activity" as const, protocol_id: id });
const protocols = ["A", "B", "C"].map(
  (id) => ({ id, name: `Assay ${id}`, readout_definitions: [] }) as unknown as Protocol,
);

describe("scientific query summaries", () => {
  it("keeps nested AND/OR groups and negation explicit", () => {
    const query: SearchQuery = {
      criteria: [
        assay("A"),
        { type: "group", logic: "or", criteria: [assay("B"), { ...assay("C"), negate: true }] },
      ],
    };
    expect(querySummaryText(query, { protocols })).toBe(
      "All projects · Tested in Assay A (any run) AND (Tested in Assay B (any run) OR NOT (Tested in Assay C (any run)))",
    );
  });
  it("shows one-sided ranges and resolved project names", () => {
    expect(
      querySummaryText(
        {
          criteria: [
            { type: "project", project_ids: ["p"] },
            { type: "property", field: "molecular_weight", operator: "between", max: 450 },
          ],
        },
        { projects: [{ id: "p", name: "Kinase discovery" }] },
      ),
    ).toBe("Project: Kinase discovery AND MW ≤ 450");
  });
  it("uses the selected assay's dose unit, not an assumed µM", () => {
    const protocol = {
      id: "A",
      name: "Kinase",
      dose_unit: "nM",
      readout_definitions: [
        { id: "rd", name: "Potency", dose_response_config: { curve_type: "ic50", intercepts: [] } },
      ],
    } as unknown as Protocol;
    const query: SearchQuery = {
      criteria: [
        {
          ...assay("A"),
          run_scope: { mode: "latest" },
          where: [{ source: "dr_curve", readout_definition_id: "rd", operator: "lt", value: 100 }],
        },
      ],
    };
    expect(querySummaryText(query, { protocols: [protocol] })).toBe(
      "All projects · Tested in Kinase (latest run) where Potency (IC50) < 100 nM",
    );
  });
  it("labels any-assay potency in µM", () => {
    expect(
      querySummaryText({
        criteria: [
          {
            type: "activity",
            protocol_id: null,
            where: [
              {
                source: "dr_curve",
                readout_definition_id: "",
                intercept_key: { kind: "ic", level: 50 },
                operator: "lt",
                value: 1,
              },
            ],
          },
        ],
      }),
    ).toContain("IC50 < 1 µM");
  });
  it("compares equivalent queries without losing Boolean distinctions", () => {
    const criteria = [assay("A"), assay("B")];
    expect(searchQueryKey({ criteria })).toBe(
      searchQueryKey({ logic: "and", criteria: [...criteria].reverse() }),
    );
    expect(searchQueryKey({ criteria })).not.toBe(searchQueryKey({ logic: "or", criteria }));
  });
});

describe("querySummaryText — split columns", () => {
  it("says how a protocol's columns are split", () => {
    const protocol = { id: "A", name: "Kinase", readout_definitions: [] } as unknown as Protocol;
    const byCondition: SearchQuery = {
      criteria: [{ ...assay("A"), split: { by: "condition", condition: "ATP" } }],
    };
    const byRun: SearchQuery = {
      criteria: [
        {
          ...assay("A"),
          run_scope: { mode: "specific", run_ids: ["r1", "r2"] },
          split: { by: "run" },
        },
      ],
    };
    expect(querySummaryText(byCondition, { protocols: [protocol] })).toBe(
      "All projects · Tested in Kinase (any run, split by ATP)",
    );
    expect(querySummaryText(byRun, { protocols: [protocol] })).toBe(
      "All projects · Tested in Kinase (2 selected run(s), split by run)",
    );
  });
});
