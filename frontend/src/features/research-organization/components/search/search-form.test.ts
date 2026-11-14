import { describe, expect, it } from "vitest";
import type { SearchQuery } from "../../types";
import {
  cleanActivityCriterion,
  countSearchCriteria,
  decomposeQuery,
  hasUnpickedRuns,
} from "./search-form";

const act = (protocol_id: string) => ({ type: "activity" as const, protocol_id, where: [] });

describe("decomposeQuery", () => {
  it("round-trips 'A and (B or C)' without turning it into 'A or B or C'", () => {
    // composeCriteria emits a mixed and/or row list as [A, group(or, B, C)];
    // decomposing must give B the "and" that joins the group to A, or the
    // next Search silently ORs everything.
    const query: SearchQuery = {
      logic: "and",
      criteria: [act("A"), { type: "group", logic: "or", criteria: [act("B"), act("C")] }],
    };
    const { activityCriteria, protocolConjunctions } = decomposeQuery(query);
    expect(activityCriteria.map((c) => c.protocol_id)).toEqual(["A", "B", "C"]);
    expect(protocolConjunctions).toEqual(["and", "and", "or"]);
  });
});

describe("countSearchCriteria", () => {
  it("counts assay criteria inside OR groups instead of counting the group as one filter", () => {
    expect(
      countSearchCriteria([{ type: "group", logic: "or", criteria: [act("A"), act("B")] }]),
    ).toBe(2);
  });

  it("counts nested groups and other filters without inflating the count", () => {
    expect(
      countSearchCriteria([
        act("A"),
        {
          type: "group",
          logic: "or",
          criteria: [act("B"), { type: "group", logic: "and", criteria: [act("C")] }],
        },
        { type: "project", project_ids: ["p1", "p2"] },
      ]),
    ).toBe(4);
    expect(countSearchCriteria([])).toBe(0);
  });
});

describe("cleanActivityCriterion", () => {
  it("drops a condition split with no condition chosen", () => {
    const cleaned = cleanActivityCriterion({
      type: "activity",
      protocol_id: "p1",
      where: [],
      split: { by: "condition", condition: "" },
    });
    expect(cleaned.split).toBeUndefined();
  });

  it("keeps a complete split", () => {
    const split = { by: "condition" as const, condition: "ATP" };
    expect(
      cleanActivityCriterion({ type: "activity", protocol_id: "p1", where: [], split }).split,
    ).toEqual(split);
  });
});

describe("decomposeQuery — split", () => {
  it("keeps a saved search's split on its protocol row", () => {
    const query: SearchQuery = {
      criteria: [
        {
          type: "activity",
          protocol_id: "p1",
          where: [],
          split: { by: "condition", condition: "ATP" },
        },
      ],
    };
    const { activityCriteria } = decomposeQuery(query);
    expect(activityCriteria[0].split).toEqual({ by: "condition", condition: "ATP" });
  });
});

describe("hasUnpickedRuns", () => {
  it("is unfinished while Specific runs has no run picked", () => {
    expect(hasUnpickedRuns({ ...act("p1"), run_scope: { mode: "specific", run_ids: [] } })).toBe(
      true,
    );
  });

  it("is finished once a run is picked, in either saved shape", () => {
    expect(
      hasUnpickedRuns({ ...act("p1"), run_scope: { mode: "specific", run_ids: ["r1"] } }),
    ).toBe(false);
    expect(hasUnpickedRuns({ ...act("p1"), run_scope: { mode: "specific", run_id: "r1" } })).toBe(
      false,
    );
    expect(hasUnpickedRuns({ ...act("p1"), run_scope: { mode: "latest" } })).toBe(false);
  });
});
