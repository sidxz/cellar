import { describe, expect, it } from "vitest";

import type { CampaignMeasurementResponse, CampaignResponse } from "../types";
import { QC_LABEL, clearedVerdictsNote, qcForecast, qcVerdictsCleared } from "./qc-verdicts";

type Verdict = CampaignMeasurementResponse["qc_verdict"];

const cell = (qc_verdict: Verdict, holds_result = true, qc_verdict_note: string | null = null) =>
  ({ qc_verdict, holds_result, qc_verdict_note }) as CampaignMeasurementResponse;

const campaign = (verdicts: Record<string, Verdict>) =>
  ({
    results: [
      {
        id: "r1",
        measurements: Object.entries(verdicts).map(([id, qc_verdict]) => ({ id, qc_verdict })),
      },
    ],
  }) as unknown as CampaignResponse;

describe("qcVerdictsCleared", () => {
  it("counts the verdicts that went back to not tested", () => {
    const before = campaign({ a: "verified", b: "failed", c: "verified" });
    const after = campaign({ a: "not_tested", b: "not_tested", c: "verified" });
    expect(qcVerdictsCleared(before, after)).toBe(2);
  });

  it("does not count cells that left the campaign, or an unknown before", () => {
    const before = campaign({ a: "verified", b: "verified" });
    expect(qcVerdictsCleared(before, campaign({}))).toBe(0);
    expect(qcVerdictsCleared(undefined, campaign({ a: "not_tested" }))).toBe(0);
  });
});

describe("clearedVerdictsNote", () => {
  it("is empty for none, singular for one, plural otherwise", () => {
    expect(clearedVerdictsNote(0)).toBe("");
    expect(clearedVerdictsNote(1)).toBe(
      " · 1 QC verdict went back to Not tested because its value changed",
    );
    expect(clearedVerdictsNote(12)).toBe(
      " · 12 QC verdicts went back to Not tested because their values changed",
    );
  });
});

describe("QC_LABEL", () => {
  it("uses the bench words", () => {
    expect(QC_LABEL).toEqual({ not_tested: "Not tested", verified: "Verified", failed: "Failed" });
  });
});

describe("qcForecast", () => {
  const cells = [
    cell("not_tested"),
    cell("verified"),
    cell("failed"),
    cell("not_tested", false),
    cell("failed", false),
  ];

  it("skips marked cells without overwrite, and cells with no result", () => {
    expect(qcForecast(cells, "verified", false)).toBe(1);
  });

  it("with overwrite also counts the other verdict, never the same one", () => {
    expect(qcForecast(cells, "verified", true)).toBe(2);
    expect(qcForecast(cells, "failed", true)).toBe(2);
  });

  it("clearing counts every marked cell, even one that no longer holds a result", () => {
    expect(qcForecast(cells, "not_tested", false)).toBe(3);
  });

  it("with overwrite and a note named, also counts same-verdict cells whose note differs", () => {
    const noted = [cell("verified", true, "clean"), cell("verified"), cell("verified", false)];
    expect(qcForecast(noted, "verified", true)).toBe(0);
    expect(qcForecast(noted, "verified", false, "other")).toBe(0);
    expect(qcForecast(noted, "verified", true, "other")).toBe(2);
    expect(qcForecast(noted, "verified", true, " clean ")).toBe(1);
    expect(qcForecast(noted, "verified", true, null)).toBe(1);
    expect(qcForecast(noted, "verified", true, "")).toBe(1);
  });
});
