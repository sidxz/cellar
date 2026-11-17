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
    observer.fire(sized(300, 200), observer as unknown as ResizeObserver);
    expect(resize).toHaveBeenCalledWith(gd);

    unmount();
    expect(observer.disconnect).toHaveBeenCalled();
  });

  it("skips the observer's first report and any other that keeps the drawn size", () => {
    vi.stubGlobal("ResizeObserver", FakeObserver);
    const resize = vi.fn(() => Promise.resolve());
    (window as { Plotly?: unknown }).Plotly = { Plots: { resize } };
    render(<Plot data={[]} layout={{}} useResizeHandler />);
    const gd = document.createElement("div");
    gd.getBoundingClientRect = () => ({ width: 300, height: 200 }) as DOMRect;
    act(() => (received.at(-1)?.onInitialized as (f: unknown, el: HTMLElement) => void)({}, gd));

    const [observer] = FakeObserver.all;
    const fire = (w: number, h: number) =>
      observer.fire(sized(w, h), observer as unknown as ResizeObserver);
    fire(300, 200);
    fire(300.4, 199.7);
    expect(resize).not.toHaveBeenCalled();
    fire(150, 200);
    expect(resize).toHaveBeenCalledTimes(1);
    fire(150, 200);
    expect(resize).toHaveBeenCalledTimes(1);
  });
});

const sized = (width: number, height: number) =>
  [{ contentRect: { width, height } }] as unknown as ResizeObserverEntry[];
