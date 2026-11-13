import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TemperatureWindowDialog } from "./temperature-window-dialog";

const customInstance = vi.fn();
vi.mock("@/shared/lib/api/custom-instance", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/shared/lib/api/custom-instance")>()),
  customInstance: (...args: unknown[]) => customInstance(...args),
}));

let channels: { key: string; label: string }[] = [];
vi.mock("../hooks/use-curve-positions", () => ({
  useCurvePositions: () => ({ data: { runs: [{ channels }, { channels }] } }),
}));

// Radix Select does not open under jsdom; a native select keeps the value contract.
vi.mock("@/shared/components/ui/select", () => ({
  Select: ({
    value,
    onValueChange,
    children,
  }: {
    value: string;
    onValueChange: (v: string) => void;
    children: ReactNode;
  }) => (
    <select aria-label="Signal" value={value} onChange={(e) => onValueChange(e.target.value)}>
      <option value="" />
      {children}
    </select>
  ),
  SelectTrigger: () => null,
  SelectValue: () => null,
  SelectContent: ({ children }: { children: ReactNode }) => <>{children}</>,
  SelectItem: ({ value, children }: { value: string; children: ReactNode }) => (
    <option value={value}>{children}</option>
  ),
}));

function renderDialog() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  render(<TemperatureWindowDialog open onOpenChange={vi.fn()} protocolId="p1" />, { wrapper });
}

function fill(name = "Main", low = "50", high = "85") {
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: name } });
  fireEvent.change(screen.getByLabelText("Signal"), { target: { value: "ch1" } });
  fireEvent.change(screen.getByLabelText("Low (°C)"), { target: { value: low } });
  fireEvent.change(screen.getByLabelText("High (°C)"), { target: { value: high } });
}

const save = () => screen.getByRole("button", { name: /add window/i });

describe("TemperatureWindowDialog", () => {
  beforeEach(() => {
    customInstance.mockReset();
    channels = [{ key: "ch1", label: "Ratio 350/330" }];
  });

  it("sends name, channel key, bounds and both measures", async () => {
    customInstance.mockResolvedValue({});
    renderDialog();
    fill();
    fireEvent.click(save());
    await waitFor(() =>
      expect(customInstance).toHaveBeenCalledWith({
        url: "/api/v1/protocols/p1/temperature-windows",
        method: "POST",
        data: {
          window: "Main",
          channel_key: "ch1",
          low: 50,
          high: 85,
          measures: ["tm", "delta_tm"],
        },
      }),
    );
  });

  it("disables Save until low < high and a measure is ticked", () => {
    renderDialog();
    fill("Main", "85", "50");
    expect(save()).toBeDisabled();
    expect(screen.getByText("Low must be below High.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("High (°C)"), { target: { value: "90" } });
    expect(save()).toBeEnabled();
    expect(screen.queryByText("Low must be below High.")).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Tm"));
    fireEvent.click(screen.getByLabelText("ΔTm"));
    expect(save()).toBeDisabled();
  });

  it("starts empty each time it opens", () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { rerender } = render(
      <TemperatureWindowDialog open onOpenChange={vi.fn()} protocolId="p1" />,
      { wrapper },
    );
    fill("Low", "25", "50");
    rerender(<TemperatureWindowDialog open={false} onOpenChange={vi.fn()} protocolId="p1" />);
    rerender(<TemperatureWindowDialog open onOpenChange={vi.fn()} protocolId="p1" />);
    expect(screen.getByLabelText("Name")).toHaveValue("");
    expect(screen.getByLabelText("Low (°C)")).toHaveValue(null);
    expect(screen.getByLabelText("High (°C)")).toHaveValue(null);
  });

  it("tells the user to import a run when the protocol has no traces", () => {
    channels = [];
    renderDialog();
    expect(
      screen.getByText(
        "Import a run with traces first; the window's signal comes from its traces.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
  });

  it("shows the API's error", async () => {
    const { ApiError } = await import("@/shared/lib/api/custom-instance");
    customInstance.mockRejectedValueOnce(
      new ApiError("API error: 409", 409, {
        message: "A readout named 'Tm (Main)' already exists",
      }),
    );
    renderDialog();
    fill();
    fireEvent.click(save());
    expect(
      await screen.findByText("A readout named 'Tm (Main)' already exists"),
    ).toBeInTheDocument();
  });
});
