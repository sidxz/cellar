import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

interface Post {
  url: string;
  data: { well_ids: string[]; channel: string; view: string; window?: number | null };
}

const posts: Post[] = [];
// The answer to each request; by default every id asked for has a curve.
let answer: (p: Post) => Promise<unknown>;

vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: vi.fn((req: Post) => {
    posts.push(req);
    return answer(req);
  }),
}));

import { useCurvesForPositions } from "./use-curves-for-positions";

function curvesFor(p: Post, opts: { window?: number | null; without?: string[] } = {}) {
  return {
    channel: p.data.channel,
    view: p.data.view,
    window: opts.window !== undefined ? opts.window : (p.data.window ?? null),
    curves: p.data.well_ids
      .filter((id) => !opts.without?.includes(id))
      .map((id) => ({ well_id: id, x: [20, 21], y: [1, 2], reported: [] })),
  };
}

const ids = (n: number, from = 0) => Array.from({ length: n }, (_, i) => `w${from + i + 1}`);

type Params = Parameters<typeof useCurvesForPositions>[1];
const measured: Params = { channel: "a", view: "measured", window: undefined };

function render(initial: { wellIds: string[]; params: Params }) {
  return renderHook(({ wellIds, params }) => useCurvesForPositions(wellIds, params), {
    initialProps: initial,
  });
}

beforeEach(() => {
  posts.length = 0;
  answer = async (p) => curvesFor(p);
});

describe("useCurvesForPositions", () => {
  it("splits 250 positions into requests of 100, 100 and 50", async () => {
    const { result } = render({ wellIds: ids(250), params: measured });
    await waitFor(() => expect(result.current.curves.size).toBe(250));
    expect(posts.map((p) => p.data.well_ids.length)).toEqual([100, 100, 50]);
    expect(posts[0].url).toBe("/api/v1/measured-curves:batch");
    expect(result.current.pending).toBe(false);
  });

  it("keeps what it has: adding one position requests only that one", async () => {
    const { result, rerender } = render({ wellIds: ids(3), params: measured });
    await waitFor(() => expect(result.current.curves.size).toBe(3));
    rerender({ wellIds: ids(4), params: measured });
    await waitFor(() => expect(result.current.curves.size).toBe(4));
    expect(posts.map((p) => p.data.well_ids)).toEqual([ids(3), ["w4"]]);
    // Shrinking the selection asks nothing and keeps the curves.
    rerender({ wellIds: ids(2), params: measured });
    await act(async () => {});
    expect(posts).toHaveLength(2);
    expect(result.current.curves.has("w3")).toBe(true);
  });

  it("sends the first response's window with the later requests of a derivative selection", async () => {
    answer = async (p) => curvesFor(p, { window: p.data.window ?? 3.5 });
    const { result } = render({
      wellIds: ids(250),
      params: { channel: "a", view: "derivative", window: undefined },
    });
    await waitFor(() => expect(result.current.curves.size).toBe(250));
    expect(posts.map((p) => p.data.window ?? null)).toEqual([null, 3.5, 3.5]);
    expect(posts.every((p) => p.data.view === "derivative")).toBe(true);
    expect(result.current.window).toBe(3.5);
  });

  it("asks nothing and reports tooMany above 400", async () => {
    const { result } = render({ wellIds: ids(401), params: measured });
    await act(async () => {});
    expect(posts).toHaveLength(0);
    expect(result.current.tooMany).toBe(true);
  });

  it("does not ask again for a position the API returned no curve for", async () => {
    answer = async (p) => curvesFor(p, { without: ["w2"] });
    const { result, rerender } = render({ wellIds: ids(2), params: measured });
    await waitFor(() => expect(result.current.curves.size).toBe(1));
    rerender({ wellIds: ids(3), params: measured });
    await waitFor(() => expect(result.current.curves.size).toBe(2));
    expect(posts.map((p) => p.data.well_ids)).toEqual([ids(2), ["w3"]]);
    expect(result.current.curves.has("w2")).toBe(false);
  });

  it("starts again when the signal, the view or the asked window changes", async () => {
    const { result, rerender } = render({ wellIds: ids(2), params: measured });
    await waitFor(() => expect(posts).toHaveLength(1));
    await waitFor(() => expect(result.current.pending).toBe(false));
    const steps: Params[] = [
      { channel: "b", view: "measured", window: undefined },
      { channel: "b", view: "derivative", window: undefined },
      { channel: "b", view: "derivative", window: 2 },
    ];
    for (const [i, params] of steps.entries()) {
      rerender({ wellIds: ids(2), params });
      await waitFor(() => expect(posts).toHaveLength(i + 2));
      await waitFor(() => expect(result.current.pending).toBe(false));
    }
    expect(posts.map((p) => [p.data.channel, p.data.view, p.data.window ?? null])).toEqual([
      ["a", "measured", null],
      ["b", "measured", null],
      ["b", "derivative", null],
      ["b", "derivative", 2],
    ]);
    expect(posts.every((p) => p.data.well_ids.length === 2)).toBe(true);
    expect(result.current.window).toBe(2);
  });

  it("drops the answer to a request of an earlier signal", async () => {
    let release: (() => void) | undefined;
    answer = (p) =>
      p.data.channel === "a"
        ? new Promise((resolve) => {
            release = () =>
              resolve({
                ...curvesFor(p),
                curves: [{ well_id: "w1", x: [0], y: [99], reported: [] }],
              });
          })
        : Promise.resolve(curvesFor(p));
    const { result, rerender } = render({ wellIds: ids(1), params: measured });
    await waitFor(() => expect(release).toBeDefined());
    rerender({ wellIds: ids(1), params: { ...measured, channel: "b" } });
    await act(async () => release?.());
    await waitFor(() => expect(posts).toHaveLength(2));
    await waitFor(() => expect(result.current.pending).toBe(false));
    expect(posts[1].data.channel).toBe("b");
    expect(result.current.curves.get("w1")?.y).toEqual([1, 2]);
  });

  it("reports a failed request, keeps what it has and asks again on retry", async () => {
    const { result, rerender } = render({ wellIds: ids(1), params: measured });
    await waitFor(() => expect(result.current.curves.size).toBe(1));
    answer = async () => {
      throw new Error("API error: 500");
    };
    rerender({ wellIds: ids(2), params: measured });
    await waitFor(() => expect(result.current.failed).toBe(true));
    expect(result.current.curves.has("w1")).toBe(true);
    answer = async (p) => curvesFor(p);
    act(() => result.current.retry());
    await waitFor(() => expect(result.current.curves.size).toBe(2));
    expect(result.current.failed).toBe(false);
    expect(posts.map((p) => p.data.well_ids)).toEqual([["w1"], ["w2"], ["w2"]]);
  });

  it("stops reporting a failure once nothing it failed to fetch is wanted", async () => {
    const { result, rerender } = render({ wellIds: ids(1), params: measured });
    await waitFor(() => expect(result.current.curves.size).toBe(1));
    answer = async () => {
      throw new Error("API error: 500");
    };
    rerender({ wellIds: ids(2), params: measured });
    await waitFor(() => expect(result.current.failed).toBe(true));
    // Back to what was fetched: nothing is missing.
    rerender({ wellIds: ids(1), params: measured });
    expect(result.current.failed).toBe(false);
    rerender({ wellIds: ids(2), params: measured });
    await waitFor(() => expect(result.current.failed).toBe(true));
    rerender({ wellIds: [], params: measured });
    expect(result.current.failed).toBe(false);
  });
});
