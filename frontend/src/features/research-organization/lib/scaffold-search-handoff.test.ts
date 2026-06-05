import { afterEach, describe, expect, it } from "vitest";
import { STORAGE_KEY, consumeScaffoldSearch, stashScaffoldSearch } from "./scaffold-search-handoff";

afterEach(() => {
  if (typeof window !== "undefined") {
    window.sessionStorage.removeItem(STORAGE_KEY);
  }
});

describe("scaffold-search-handoff", () => {
  it("stashes a scaffold criterion and consume() returns it", () => {
    stashScaffoldSearch("c1ccncc1");
    const result = consumeScaffoldSearch();
    expect(result).toEqual({
      type: "scaffold",
      mode: "exact_match",
      scaffold_smiles: "c1ccncc1",
    });
  });

  it("consume() clears the storage on read (one-shot)", () => {
    stashScaffoldSearch("c1ccncc1");
    consumeScaffoldSearch();
    expect(window.sessionStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("consume() returns null when nothing is stashed", () => {
    expect(consumeScaffoldSearch()).toBeNull();
  });

  it("consume() returns null and clears storage on malformed JSON", () => {
    window.sessionStorage.setItem(STORAGE_KEY, "not-json{");
    expect(consumeScaffoldSearch()).toBeNull();
    expect(window.sessionStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("stashes the NO_SCAFFOLD sentinel as acyclic_only mode", () => {
    stashScaffoldSearch("");
    expect(consumeScaffoldSearch()).toEqual({
      type: "scaffold",
      mode: "acyclic_only",
    });
  });

  it("consume() returns null if mode is exact_match but scaffold_smiles is missing", () => {
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ type: "scaffold", mode: "exact_match" }),
    );
    expect(consumeScaffoldSearch()).toBeNull();
    expect(window.sessionStorage.getItem(STORAGE_KEY)).toBeNull();
  });
});
