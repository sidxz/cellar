import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { type DerivedSet, type DerivedSpec, type SeriesMember, letters } from "../lib/derived";
import { type DerivedEntry, derivedReducer, runnable, setsOf, useDerived } from "./use-derived";

const rg1: DerivedSpec = {
  id: "rg1",
  kind: "rgroups",
  coreSmiles: "c1ccccc1[*:1]",
  name: "Core A",
};
const clusters: DerivedSpec = { id: "clusters", kind: "clusters", threshold: 0.4 };
const series = (...members: SeriesMember[]): DerivedSpec => ({
  id: "series",
  kind: "series",
  members,
});
const setOf = (spec: DerivedSpec): DerivedSet => ({
  spec,
  columns: [],
  byMolecule: new Map(),
  summary: "",
});

const add = (entries: DerivedEntry[], spec: DerivedSpec, ids = ["m1", "m2"]) =>
  derivedReducer(entries, { type: "add", spec, moleculeIds: ids });

describe("runnable", () => {
  it("holds a series back while an R-groups set it names is still running", () => {
    const both = add(add(add([], rg1), clusters), series({ name: "Series A", rgroupsId: "rg1" }));
    expect(runnable(both).map((e) => e.spec.id)).toEqual(["rg1", "clusters"]);
    const ready = derivedReducer(both, { type: "resolve", id: "rg1", set: setOf(rg1) });
    expect(runnable(ready).map((e) => e.spec.id)).toEqual(["clusters", "series"]);
    const failed = derivedReducer(both, { type: "fail", id: "rg1", message: "No match." });
    expect(runnable(failed).map((e) => e.spec.id)).toEqual(["clusters", "series"]);
  });
});

describe("derivedReducer", () => {
  it("adds a running entry over the given compounds; adding the same id replaces it", () => {
    const one = add([], rg1);
    expect(one).toEqual([
      expect.objectContaining({
        spec: rg1,
        moleculeIds: ["m1", "m2"],
        status: "running",
        attempt: 1,
      }),
    ]);
    const ready = derivedReducer(one, { type: "resolve", id: "rg1", set: setOf(rg1) });
    const again = add(ready, { ...rg1, coreSmiles: "C1CCCCC1[*:1]" }, ["m3"]);
    expect(again).toHaveLength(1);
    expect(again[0]).toMatchObject({ status: "running", moleculeIds: ["m3"], attempt: 2 });
    expect(again[0].set).toBeUndefined();
  });

  it("resolves a running entry and ignores a late answer for one no longer running", () => {
    const set = setOf(rg1);
    const ready = derivedReducer(add([], rg1), { type: "resolve", id: "rg1", set });
    expect(ready[0]).toMatchObject({ status: "ready", set });
    const cancelled = derivedReducer(add([], rg1), { type: "cancel", id: "rg1" });
    expect(derivedReducer(cancelled, { type: "resolve", id: "rg1", set })).toBe(cancelled);
    expect(derivedReducer(cancelled, { type: "fail", id: "rg1", message: "x" })).toBe(cancelled);
  });

  it("a failure keeps its message until Retry starts the next attempt", () => {
    const failed = derivedReducer(add([], clusters), {
      type: "fail",
      id: "clusters",
      message: "Cluster map capped at 50000 molecules; refine the filter.",
    });
    expect(failed[0]).toMatchObject({
      status: "failed",
      error: "Cluster map capped at 50000 molecules; refine the filter.",
    });
    const retried = derivedReducer(failed, { type: "retry", id: "clusters" });
    expect(retried[0]).toMatchObject({ status: "running", attempt: 2 });
    expect(retried[0].error).toBeUndefined();
  });

  it("recompute runs over the new compounds and keeps the last columns until it answers", () => {
    const set = setOf(rg1);
    const ready = derivedReducer(add([], rg1), { type: "resolve", id: "rg1", set });
    const next = derivedReducer(ready, { type: "recompute", id: "rg1", moleculeIds: ["m1", "m9"] });
    expect(next[0]).toMatchObject({ status: "running", moleculeIds: ["m1", "m9"], set });
    expect(setsOf(next)).toEqual([set]);
  });

  it("removing an R-groups set strips the series members that point at it", () => {
    let entries = add([], rg1);
    entries = add(
      entries,
      series({ name: "Series A", rgroupsId: "rg1" }, { name: "Series B", scaffold: "c1ccncc1" }),
    );
    entries = derivedReducer(entries, {
      type: "resolve",
      id: "series",
      set: setOf(entries[1].spec),
    });
    const after = derivedReducer(entries, { type: "remove", id: "rg1" });
    expect(after.map((e) => e.spec.id)).toEqual(["series"]);
    expect(after[0].spec).toMatchObject({ members: [{ name: "Series B", scaffold: "c1ccncc1" }] });
    // Recomputed without the member, showing its last columns meanwhile.
    expect(after[0]).toMatchObject({ status: "running" });
    expect(after[0].set).toBeDefined();
  });

  it("drops a series left without members", () => {
    let entries = add([], rg1);
    entries = add(entries, series({ name: "Series A", rgroupsId: "rg1" }));
    expect(derivedReducer(entries, { type: "remove", id: "rg1" })).toEqual([]);
  });
});

describe("useDerived", () => {
  it("keeps the same sets array while only job states change", () => {
    const set = setOf(rg1);
    const ready: DerivedEntry = {
      spec: rg1,
      moleculeIds: [],
      status: "ready",
      set,
      startedAt: 0,
      attempt: 1,
    };
    const { result } = renderHook(() => useDerived([ready]));
    const before = result.current.readySets;
    expect(before).toEqual([set]);
    act(() => result.current.dispatch({ type: "add", spec: clusters, moleculeIds: ["m1"] }));
    act(() => result.current.dispatch({ type: "fail", id: "clusters", message: "x" }));
    expect(result.current.readySets).toBe(before);
    act(() => result.current.dispatch({ type: "remove", id: "rg1" }));
    expect(result.current.readySets).toEqual([]);
  });
});

describe("useDerived newRGroups", () => {
  it("never reuses an R-groups id or name in one workbench, even after a removal", () => {
    const { result } = renderHook(() => useDerived());
    const first = result.current.newRGroups("c1ccccc1[*:1]");
    expect(first).toEqual({
      id: "rg1",
      kind: "rgroups",
      coreSmiles: "c1ccccc1[*:1]",
      name: "Core A",
    });
    act(() => result.current.dispatch({ type: "add", spec: first, moleculeIds: ["m1"] }));
    act(() => result.current.dispatch({ type: "remove", id: "rg1" }));
    // Undo history may still name chem:rg1 columns: the next set is rg2, whatever is left.
    expect(result.current.newRGroups("c1ccncc1[*:1]")).toMatchObject({ id: "rg2", name: "Core B" });
    expect(result.current.newRGroups("C1CCCCC1[*:1]")).toMatchObject({ id: "rg3", name: "Core C" });
  });

  it("continues after the sets it has held, removed or not", () => {
    const seeded: DerivedEntry = {
      spec: { ...rg1, id: "rg4", name: "Core D" },
      moleculeIds: [],
      status: "running",
      startedAt: 0,
      attempt: 1,
    };
    const { result } = renderHook(() => useDerived([seeded]));
    // Removed before any new set: its id is still taken.
    act(() => result.current.dispatch({ type: "remove", id: "rg4" }));
    expect(result.current.newRGroups("c1ccccc1[*:1]")).toMatchObject({ id: "rg5", name: "Core E" });
  });

  it("names sets past Z like spreadsheet columns", () => {
    expect([1, 26, 27, 52, 53].map(letters)).toEqual(["A", "Z", "AA", "AZ", "BA"]);
  });
});
