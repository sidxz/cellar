import { beforeEach, describe, expect, it } from "vitest";

import { FONT_SCALE_DEFAULT, useFontScaleStore } from "./font-scale-store";

describe("font-scale-store", () => {
  beforeEach(() => {
    useFontScaleStore.getState().reset();
  });

  it("clamps setScale to the 80-120 range", () => {
    useFontScaleStore.getState().setScale(300);
    expect(useFontScaleStore.getState().scale).toBe(120);
    useFontScaleStore.getState().setScale(10);
    expect(useFontScaleStore.getState().scale).toBe(80);
  });

  it("accepts in-range values and resets to default", () => {
    useFontScaleStore.getState().setScale(110);
    expect(useFontScaleStore.getState().scale).toBe(110);
    useFontScaleStore.getState().reset();
    expect(useFontScaleStore.getState().scale).toBe(FONT_SCALE_DEFAULT);
  });

  it("clamps an out-of-range persisted value on rehydrate", async () => {
    localStorage.setItem("ds-font-scale", JSON.stringify({ state: { scale: 500 }, version: 0 }));
    await useFontScaleStore.persist.rehydrate();
    expect(useFontScaleStore.getState().scale).toBe(120);
  });
});
