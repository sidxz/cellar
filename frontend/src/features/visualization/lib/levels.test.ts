import { describe, expect, it } from "vitest";
import { LEVEL_ORDER, countsAtLevel } from "./levels";

describe("levels", () => {
  it("orders the four levels from finest to coarsest", () => {
    expect(LEVEL_ORDER).toEqual(["wells", "runs", "batches", "compounds"]);
  });

  it("counts only completed or approved runs at Batches and Compounds", () => {
    expect(countsAtLevel("compounds", "draft")).toBe(false);
    expect(countsAtLevel("batches", "in_progress")).toBe(false);
    expect(countsAtLevel("compounds", "completed")).toBe(true);
    expect(countsAtLevel("batches", "approved")).toBe(true);
    expect(countsAtLevel("runs", "draft")).toBe(true);
    expect(countsAtLevel("wells", "draft")).toBe(true);
  });
});
