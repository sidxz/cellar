import { describe, expect, it } from "vitest";

import { readProtocolLink, resolveProtocolLink, withoutProtocolLink } from "./protocol-link";

describe("readProtocolLink", () => {
  it("is null unless the link asks for a new protocol", () => {
    expect(readProtocolLink(new URLSearchParams("category=X"))).toBeNull();
    expect(readProtocolLink(new URLSearchParams())).toBeNull();
  });

  it("reads every target and leaves what is not sent empty", () => {
    expect(readProtocolLink(new URLSearchParams("new_protocol=1&target_id=a&target_id=b"))).toEqual(
      { category: null, protocolType: null, targetIds: ["a", "b"], projectId: null },
    );
  });

  it("reads category, type and project", () => {
    expect(
      readProtocolLink(
        new URLSearchParams(
          "new_protocol=1&category=Growth+inhibition&protocol_type=whole_cell&project_id=p1",
        ),
      ),
    ).toEqual({
      category: "Growth inhibition",
      protocolType: "whole_cell",
      targetIds: [],
      projectId: "p1",
    });
  });
});

describe("withoutProtocolLink", () => {
  it("removes the link's own values and keeps return_to", () => {
    expect(
      withoutProtocolLink(
        new URLSearchParams(
          "new_protocol=1&category=X&protocol_type=t&target_id=a&project_id=p&return_to=https%3A%2F%2Fd.org%2Fs",
        ),
      ),
    ).toBe("?return_to=https%3A%2F%2Fd.org%2Fs");
  });

  it("is empty when nothing else is left", () => {
    expect(withoutProtocolLink(new URLSearchParams("new_protocol=1&category=X"))).toBe("");
  });
});

describe("resolveProtocolLink", () => {
  const known = { categoryLabels: ["Growth inhibition"], targetIds: ["t1"], projectIds: ["p1"] };

  it("keeps what ChemCellar knows", () => {
    expect(
      resolveProtocolLink(
        {
          category: "Growth inhibition",
          protocolType: "whole_cell",
          targetIds: ["t1", "t1"],
          projectId: "p1",
        },
        known,
      ),
    ).toEqual({
      category: "Growth inhibition",
      protocolType: "whole_cell",
      targetIds: ["t1"],
      projectId: "p1",
    });
  });

  it("drops what it does not know", () => {
    expect(
      resolveProtocolLink(
        { category: "Nope", protocolType: "bogus", targetIds: ["t9", "t1"], projectId: "p9" },
        known,
      ),
    ).toEqual({ category: null, protocolType: null, targetIds: ["t1"], projectId: null });
  });
});
