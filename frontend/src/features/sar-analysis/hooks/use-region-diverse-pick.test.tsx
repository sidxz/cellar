import { describe, it, expect, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { useRegionDiversePick } from "./use-region-diverse-pick";

const wrapper = ({ children }: { children: React.ReactNode }) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
};

const resultDto = {
  points: [
    { molecule_id: "a", x: 0, y: 0 },
    { molecule_id: "b", x: 1, y: 1 },
  ],
  clusters: [
    { molecule_id: "a", cluster_id: 0 },
    { molecule_id: "b", cluster_id: 0 },
  ],
  representatives: [{ molecule_id: "a", cluster_id: 0 }],
  cluster_count: 1,
  picker: "maxmin",
  picker_params: { n: 1 },
  skipped_molecule_ids: [],
};

describe("useRegionDiversePick", () => {
  it("is idle until pick() is called", () => {
    const startFn = vi.fn();
    const { result } = renderHook(() => useRegionDiversePick({ startFn }), {
      wrapper,
    });
    expect(result.current.active).toBe(false);
    expect(result.current.pickedIds.size).toBe(0);
    expect(startFn).not.toHaveBeenCalled();
  });

  it("pick() runs MaxMin over the subset and returns representative ids", async () => {
    const startFn = vi.fn(async () => ({ result: resultDto, job: null }));
    const { result } = renderHook(() => useRegionDiversePick({ startFn }), {
      wrapper,
    });

    act(() => result.current.pick(["a", "b"], 1));

    await waitFor(() => expect(result.current.pickedIds.size).toBe(1));
    expect([...result.current.pickedIds]).toEqual(["a"]);

    const call = startFn.mock.calls[0][0];
    expect(call.picker).toBe("maxmin");
    expect(call.molecule_ids).toEqual(["a", "b"]);
    expect(call.n).toBe(1);
  });

  it("reset() clears the picks and goes idle", async () => {
    const startFn = vi.fn(async () => ({ result: resultDto, job: null }));
    const { result } = renderHook(() => useRegionDiversePick({ startFn }), {
      wrapper,
    });
    act(() => result.current.pick(["a", "b"], 1));
    await waitFor(() => expect(result.current.pickedIds.size).toBe(1));
    act(() => result.current.reset());
    expect(result.current.active).toBe(false);
    expect(result.current.pickedIds.size).toBe(0);
  });
});
