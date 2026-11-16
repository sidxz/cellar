import { act, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const received = vi.hoisted(() => [] as Record<string, unknown>[]);

vi.mock("next/dynamic", () => ({
  default: () => (props: Record<string, unknown>) => {
    received.push(props);
    return null;
  },
}));

import { Plot } from "./plotly";

/** A ResizeObserver double: records what it watches and lets the test fire it. */
class FakeObserver {
  static all: FakeObserver[] = [];
  watched: Element[] = [];
  disconnect = vi.fn();
  constructor(readonly fire: ResizeObserverCallback) {
    FakeObserver.all.push(this);
  }
  observe(el: Element) {
    this.watched.push(el);
  }
  unobserve() {}
}

afterEach(() => {
  vi.unstubAllGlobals();
  FakeObserver.all = [];
  (window as { Plotly?: unknown }).Plotly = undefined;
});

describe("Plot", () => {
  it("never offers the send-to-cloud modebar button, whatever the caller passes", () => {
    render(<Plot data={[]} layout={{}} config={{ displaylogo: false, showSendToCloud: true }} />);
    expect(received.at(-1)?.config).toEqual({ displaylogo: false, showSendToCloud: false });

    render(<Plot data={[]} layout={{}} />);
    expect(received.at(-1)?.config).toEqual({ showSendToCloud: false });
  });

  it("resizes the graph when its own box changes size, not only on a window resize", () => {
    vi.stubGlobal("ResizeObserver", FakeObserver);
    const resize = vi.fn(() => Promise.resolve());
    (window as { Plotly?: unknown }).Plotly = { Plots: { resize } };
    const onInitialized = vi.fn();
    const { unmount } = render(
      <Plot data={[]} layout={{}} useResizeHandler onInitialized={onInitialized} />,
    );
    const gd = document.createElement("div");
    act(() => (received.at(-1)?.onInitialized as (f: unknown, el: HTMLElement) => void)({}, gd));
    // The caller's own callback still runs.
    expect(onInitialized).toHaveBeenCalledWith({}, gd);

    const [observer] = FakeObserver.all;
    expect(observer.watched).toEqual([gd]);
    observer.fire([], observer as unknown as ResizeObserver);
    expect(resize).toHaveBeenCalledWith(gd);

    unmount();
    expect(observer.disconnect).toHaveBeenCalled();
  });
});
