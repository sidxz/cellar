import { describe, expect, it } from "vitest";
import { shortName } from "./short-name";

describe("shortName", () => {
  it("keeps the tail that tells two protocols apart, cutting the middle", () => {
    const nadh = "M. tuberculosis InhA inhibition [NADH oxidation]";
    const ddcoa = "M. tuberculosis InhA inhibition [DD-CoA fluorescence]";
    expect(shortName(nadh)).toBe("M. tuberculosis…[NADH oxidation]");
    expect(shortName(ddcoa)).toBe("M. tubercu…[DD-CoA fluorescence]");
    for (const n of [nadh, ddcoa]) expect(shortName(n).length).toBeLessThanOrEqual(32);
  });

  it("keeps a short name whole and splits a name without a method around its middle", () => {
    expect(shortName("Counter")).toBe("Counter");
    expect(shortName("Mtb_WCA_mc2-7000_Resazurin counter-screen", 24)).toBe(
      "Mtb_WCA_mc2…unter-screen",
    );
  });
});
