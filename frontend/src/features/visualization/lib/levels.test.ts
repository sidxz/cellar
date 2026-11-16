import { describe, expect, it } from "vitest";
import { LEVELS, LEVEL_ORDER, countsAtLevel } from "./levels";

describe("levels", () => {
  it("lists the four levels from finest to coarsest, each saying what a row is", () => {
    expect(LEVEL_ORDER).toEqual(["wells", "runs", "batches", "compounds"]);
    expect(LEVEL_ORDER.map((l) => LEVELS[l].caption)).toEqual([
      "Each row: one well",
      "Each row: compound × batch × run",
      "Each row: compound × batch",
      "Each row: compound",
    ]);
    expect(LEVELS.batches).toEqual({
      label: "Batches",
      caption: "Each row: compound × batch",
      one: "batch",
      many: "batches",
    });
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
