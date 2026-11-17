import { describe, expect, it } from "vitest";
import type { MeltingAnalysis } from "../types";
import { peaksToAccept } from "./accept-all";

type Input = Pick<MeltingAnalysis, "windows" | "steps">;

const step = (id: string, status: string, version = 1) => ({ id, status, version });
const window = (channel_key: string, stepIds: (string | null)[]) => ({
  channel_key,
  positions: stepIds.map((step_id) => ({ step_id })),
});
const analysis = (windows: unknown[], steps: unknown[]) => ({ windows, steps }) as unknown as Input;

describe("peaksToAccept", () => {
  it("takes the unreviewed peaks that give a window's value on the signal shown", () => {
    const a = analysis(
      [window("ratio", ["a", "b", null]), window("f350", ["z"])],
      [
        step("a", "unreviewed", 3),
        step("b", "accepted"),
        step("c", "unreviewed"), // outside every window: gives no value
        step("z", "unreviewed"), // another signal
      ],
    );
    expect(peaksToAccept(a, "ratio")).toEqual([{ id: "a", expected_version: 3 }]);
  });

  it("leaves out a rejected peak and a position with no naming peak", () => {
    const a = analysis([window("ratio", [null, "r"])], [step("r", "rejected")]);
    expect(peaksToAccept(a, "ratio")).toEqual([]);
  });

  it("lists a peak once when two windows on the signal name it", () => {
    const a = analysis([window("ratio", ["a"]), window("ratio", ["a"])], [step("a", "unreviewed")]);
    expect(peaksToAccept(a, "ratio")).toHaveLength(1);
  });
});
