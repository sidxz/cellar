import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReadoutDefinition } from "../types";
import { TemperatureWindowDialog } from "./temperature-window-dialog";

const melt = (name: string, measure: string, extra: Record<string, unknown> = {}) =>
  ({
    name,
    melt_config: { window: "Main", measure, channel_key: "ch1", low: 50, high: 85, ...extra },
  }) as unknown as ReadoutDefinition;
const MAIN = [melt("Tm (Main)", "tm"), melt("ΔTm (Main)", "delta_tm")];
let readouts: ReadoutDefinition[] = [];

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
  render(
    <TemperatureWindowDialog
      open
      onOpenChange={vi.fn()}
      protocolId="p1"
      readoutDefinitions={readouts}
      doseUnit="µM"
    />,
    { wrapper },
  );
}

function fill(name = "Main", low = "50", high = "85") {
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: name } });
  fireEvent.change(screen.getByLabelText("Signal"), { target: { value: "ch1" } });
  fireEvent.change(screen.getByLabelText("Low (°C)"), { target: { value: low } });
  fireEvent.change(screen.getByLabelText("High (°C)"), { target: { value: high } });
}

const save = () => screen.getByRole("button", { name: /^add (window|values)$/i });

describe("TemperatureWindowDialog", () => {
  beforeEach(() => {
    customInstance.mockReset();
    channels = [{ key: "ch1", label: "Ratio 350/330" }];
    readouts = [];
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
      <TemperatureWindowDialog
        open
        onOpenChange={vi.fn()}
        protocolId="p1"
        readoutDefinitions={[]}
        doseUnit="µM"
      />,
      { wrapper },
    );
    fill("Low", "25", "50");
    const again = (open: boolean) => (
      <TemperatureWindowDialog
        open={open}
        onOpenChange={vi.fn()}
        protocolId="p1"
        readoutDefinitions={[]}
        doseUnit="µM"
      />
    );
    rerender(again(false));
    rerender(again(true));
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

  const posted = () => customInstance.mock.calls[0][0].data;
  const pickWindow = (name: string) => fireEvent.mouseDown(screen.getByRole("tab", { name }));

  it("adds series values to a new window, nothing ticked by default", async () => {
    customInstance.mockResolvedValue({});
    renderDialog();
    fill();
    expect(screen.getByLabelText("Max ΔTm")).not.toBeChecked();
    expect(screen.getByLabelText("Lowest shifting concentration")).not.toBeChecked();
    expect(screen.getByLabelText("ΔTm at a stated concentration")).not.toBeChecked();
    fireEvent.click(screen.getByLabelText("Max ΔTm"));
    fireEvent.click(save());
    await waitFor(() => expect(customInstance).toHaveBeenCalled());
    expect(posted().measures).toEqual(["tm", "delta_tm", "max_delta_tm"]);
    expect(posted()).not.toHaveProperty("lowest_shift_threshold");
  });

  it("adds series values to an existing window, with its signal and limits", async () => {
    customInstance.mockResolvedValue({});
    readouts = MAIN;
    renderDialog();
    pickWindow("Main");
    expect(screen.getByLabelText("Low (°C)")).toHaveValue(50);
    expect(screen.getByLabelText("Low (°C)")).toBeDisabled();
    expect(screen.getByLabelText("Tm")).toBeChecked();
    expect(screen.getByLabelText("Tm")).toBeDisabled();
    expect(save()).toBeDisabled(); // nothing new chosen yet
    fireEvent.click(screen.getByLabelText("Lowest shifting concentration"));
    fireEvent.click(screen.getByLabelText("ΔTm at a stated concentration"));
    expect(save()).toBeDisabled(); // the concentration is still empty
    fireEvent.change(screen.getByLabelText("Concentration (µM)"), { target: { value: "50" } });
    fireEvent.click(save());
    await waitFor(() => expect(customInstance).toHaveBeenCalled());
    expect(posted()).toEqual({
      window: "Main",
      channel_key: "ch1",
      low: 50,
      high: 85,
      measures: ["lowest_shift_concentration", "delta_tm_at_concentration"],
      lowest_shift_threshold: 2,
      delta_tm_at_concentration: 50,
    });
  });

  it("a value the window already has is shown ticked and disabled", () => {
    readouts = [
      ...MAIN,
      melt("Max ΔTm (Main)", "max_delta_tm"),
      melt("ΔTm at 50 µM (Main)", "delta_tm_at_concentration", { concentration: 50 }),
    ];
    renderDialog();
    pickWindow("Main");
    expect(screen.getByLabelText("Max ΔTm")).toBeChecked();
    expect(screen.getByLabelText("Max ΔTm")).toBeDisabled();
    fireEvent.click(screen.getByLabelText("ΔTm at a stated concentration"));
    fireEvent.change(screen.getByLabelText("Concentration (µM)"), { target: { value: "50" } });
    expect(screen.getByText("This window already has it.")).toBeInTheDocument();
    expect(save()).toBeDisabled();
  });
});
