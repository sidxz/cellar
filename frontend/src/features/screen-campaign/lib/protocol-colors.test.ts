import { GROUP_PALETTE } from "@/shared/lib/chart-colors";
import { describe, expect, it } from "vitest";
import { protocolColorById } from "./protocol-colors";

describe("protocolColorById", () => {
  it("assigns palette slots by first appearance in display order, one per protocol", () => {
    const map = protocolColorById([
      { protocol_id: "b", display_order: 2 },
      { protocol_id: "a", display_order: 0 },
      { protocol_id: "b", display_order: 1 },
    ]);
    expect(map.get("a")).toBe(GROUP_PALETTE[0]);
    expect(map.get("b")).toBe(GROUP_PALETTE[1]);
    expect(map.size).toBe(2);
  });
});
