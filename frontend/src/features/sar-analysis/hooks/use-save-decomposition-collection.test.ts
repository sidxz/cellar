import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useSaveDecompositionCollection } from "./use-save-decomposition-collection";

describe("useSaveDecompositionCollection", () => {
  it("posts name/project/filter/projection and returns the new collection id", async () => {
    const fetchFn = vi.fn().mockResolvedValue({ collection_id: "coll-9" });
    const { result } = renderHook(() => useSaveDecompositionCollection({ fetchFn }));
    const out = await result.current.saveAll({
      runId: "run-1",
      name: "Series A",
      projectId: "p1",
      filter: { molecular_weight: { kind: "number", op: "gt", value: 400 } },
      projectionId: "proj-1",
    });
    expect(out).toEqual({ collection_id: "coll-9" });
    expect(fetchFn).toHaveBeenCalledWith("run-1", {
      name: "Series A",
      project_id: "p1",
      filter: { molecular_weight: { kind: "number", op: "gt", value: 400 } },
      projection_id: "proj-1",
    });
  });

  it("omits filter/projection when not provided", async () => {
    const fetchFn = vi.fn().mockResolvedValue({ collection_id: "coll-1" });
    const { result } = renderHook(() => useSaveDecompositionCollection({ fetchFn }));
    await result.current.saveAll({ runId: "run-1", name: "All", projectId: null });
    expect(fetchFn).toHaveBeenCalledWith("run-1", {
      name: "All",
      project_id: null,
      filter: undefined,
      projection_id: undefined,
    });
  });
});
