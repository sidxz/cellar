import { describe, expect, it } from "vitest";
import type { CampaignChannelResponse, CampaignStageResponse } from "../types";
import { OTHER_COLUMNS, groupColumnsByStage, stagesInFunnelOrder } from "./stage-column-groups";

function stage(
  id: string,
  display_order: number,
  parent_stage_id: string | null = null,
): CampaignStageResponse {
  return { id, name: id, display_order, parent_stage_id } as CampaignStageResponse;
}

function column(
  id: string,
  stage_id: string | null,
  display_order: number,
): CampaignChannelResponse {
  return { id, stage_id, display_order } as CampaignChannelResponse;
}

describe("stagesInFunnelOrder", () => {
  it("puts a parent before its children even when a child sorts first", () => {
    const order = stagesInFunnelOrder([stage("retest", 0, "primary"), stage("primary", 1)]);
    expect(order.map((s) => s.id)).toEqual(["primary", "retest"]);
  });

  it("follows each root with its own children, siblings by display_order", () => {
    const order = stagesInFunnelOrder([
      stage("counter", 1),
      stage("primary", 0),
      stage("dose", 5, "retest"),
      stage("retest", 3, "primary"),
      stage("confirm", 2, "primary"),
    ]);
    expect(order.map((s) => s.id)).toEqual(["primary", "confirm", "retest", "dose", "counter"]);
  });

  it("treats a stage whose parent is gone as a root", () => {
    const order = stagesInFunnelOrder([stage("b", 1), stage("orphan", 0, "missing")]);
    expect(order.map((s) => s.id)).toEqual(["orphan", "b"]);
  });
});

describe("groupColumnsByStage", () => {
  const stages = [stage("retest", 0, "primary"), stage("primary", 1), stage("empty", 2)];

  it("groups by stage in funnel order, campaign columns last under Other columns", () => {
    const groups = groupColumnsByStage(
      [
        column("counter", null, 0),
        column("retest-inh", "retest", 1),
        column("primary-ic50", "primary", 4),
        column("primary-inh", "primary", 2),
      ],
      stages,
    );
    expect(groups.map((g) => [g.stageId, g.title, g.channels.map((c) => c.id)])).toEqual([
      ["primary", "primary", ["primary-inh", "primary-ic50"]],
      ["retest", "retest", ["retest-inh"]],
      [null, OTHER_COLUMNS, ["counter"]],
    ]);
  });

  it("leaves out stages with no columns, and files a column of an unknown stage under Other columns", () => {
    const groups = groupColumnsByStage([column("stray", "deleted-stage", 0)], stages);
    expect(groups).toEqual([
      { stageId: null, title: OTHER_COLUMNS, channels: [column("stray", "deleted-stage", 0)] },
    ]);
  });
});
