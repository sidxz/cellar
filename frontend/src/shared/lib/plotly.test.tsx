import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const received = vi.hoisted(() => [] as Record<string, unknown>[]);

vi.mock("next/dynamic", () => ({
  default: () => (props: Record<string, unknown>) => {
    received.push(props);
    return null;
  },
}));

import { Plot } from "./plotly";

describe("Plot", () => {
  it("never offers the send-to-cloud modebar button, whatever the caller passes", () => {
    render(<Plot data={[]} layout={{}} config={{ displaylogo: false, showSendToCloud: true }} />);
    expect(received.at(-1)?.config).toEqual({ displaylogo: false, showSendToCloud: false });

    render(<Plot data={[]} layout={{}} />);
    expect(received.at(-1)?.config).toEqual({ showSendToCloud: false });
  });
});
