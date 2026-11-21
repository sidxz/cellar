import { describe, expect, it } from "vitest";

import { parseReturnOrigins, returnHref, trustedReturnTarget } from "./return-to";

describe("parseReturnOrigins", () => {
  it("reads Label=origin entries and keeps only the origin", () => {
    expect(
      parseReturnOrigins("Daikon=https://daikon.example.org, Other=http://localhost:5173/"),
    ).toEqual([
      { label: "Daikon", origin: "https://daikon.example.org" },
      { label: "Other", origin: "http://localhost:5173" },
    ]);
  });

  it("drops entries that are not a label and an http(s) origin", () => {
    expect(
      parseReturnOrigins(
        " , nolabel, =https://a.org, X=not a url, X=ftp://a.org, X=javascript:alert(1), Ok=https://ok.org",
      ),
    ).toEqual([{ label: "Ok", origin: "https://ok.org" }]);
  });

  it("is empty when the setting is missing or blank", () => {
    expect(parseReturnOrigins(undefined)).toEqual([]);
    expect(parseReturnOrigins("")).toEqual([]);
  });
});

describe("trustedReturnTarget", () => {
  const origins = [{ label: "Daikon", origin: "https://daikon.example.org" }];

  it("trusts an address on a configured origin, as given", () => {
    const url = "https://daikon.example.org/screens/7?round=2";
    expect(trustedReturnTarget(url, origins)).toEqual({ label: "Daikon", url });
  });

  it.each([
    "https://daikon.example.org.evil.com/x",
    "https://daikon.example.org:8443/x",
    "http://daikon.example.org/x",
    "//daikon.example.org/x",
    "javascript:alert(1)",
    "",
  ])("ignores %s", (url) => {
    expect(trustedReturnTarget(url, origins)).toBeNull();
  });

  it("ignores everything when nothing is configured or nothing was sent", () => {
    expect(trustedReturnTarget(null, origins)).toBeNull();
    expect(trustedReturnTarget("https://daikon.example.org/x", [])).toBeNull();
  });
});

describe("returnHref", () => {
  const target = { label: "Daikon", url: "https://d.org/s?round=2&protocol_id=old#stage" };

  it("sets protocol_id and keeps the rest of the address", () => {
    expect(returnHref(target, "abc")).toBe("https://d.org/s?round=2&protocol_id=abc#stage");
  });

  it("returns the address unchanged without an id", () => {
    expect(returnHref(target)).toBe(target.url);
  });
});
