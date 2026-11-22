import { describe, expect, it } from "vitest";
import { canChangeOwner } from "./use-change-owner";

const me = (over = {}) => ({ user_id: "u1", is_admin: false, workspace_role: "editor", ...over });

describe("canChangeOwner", () => {
  it("lets the creator and an admin change the owner, not another editor or a viewer", () => {
    expect(canChangeOwner(me(), "u1")).toBe(true);
    expect(
      canChangeOwner(me({ user_id: "u2", is_admin: true, workspace_role: "admin" }), "u1"),
    ).toBe(true);
    expect(canChangeOwner(me({ user_id: "u2" }), "u1")).toBe(false);
    expect(canChangeOwner(me({ workspace_role: "viewer" }), "u1")).toBe(false);
    expect(canChangeOwner(undefined, "u1")).toBe(false);
  });
});
