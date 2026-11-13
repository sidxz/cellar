import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

const mutate = vi.fn();
vi.mock("../hooks/use-runs", () => ({ useCreateRun: () => ({ mutate, isPending: false }) }));
vi.mock("../hooks/use-plate-templates", () => ({ usePlateTemplates: () => ({ data: [] }) }));
vi.mock("./target-multi-select", () => ({ TargetMultiSelect: () => null }));

import { CreateRunDialog } from "./create-run-dialog";

// Radix Select needs these on items; jsdom ships neither.
beforeAll(() => {
  if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = vi.fn();
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = vi.fn(() => false);
  }
  if (!Element.prototype.releasePointerCapture) {
    Element.prototype.releasePointerCapture = vi.fn();
  }
});

beforeEach(() => mutate.mockReset());

function renderDialog() {
  render(<CreateRunDialog protocolId="p1" open onOpenChange={vi.fn()} />);
}

describe("CreateRunDialog plate format", () => {
  it("defaults to 96-well and sends it", async () => {
    renderDialog();
    expect(screen.getByRole("combobox")).toHaveTextContent("96-Well");
    fireEvent.click(screen.getByRole("button", { name: /create run/i }));
    await waitFor(() => expect(mutate).toHaveBeenCalled());
    expect(mutate.mock.calls[0][0]).toMatchObject({ protocol_id: "p1", plate_format: "96" });
  });

  it("sends no plate format when No plate is chosen", async () => {
    renderDialog();
    fireEvent.click(screen.getByRole("combobox"));
    fireEvent.click(await screen.findByRole("option", { name: "No plate" }));
    expect(screen.getByRole("combobox")).toHaveTextContent("No plate");
    fireEvent.click(screen.getByRole("button", { name: /create run/i }));
    await waitFor(() => expect(mutate).toHaveBeenCalled());
    const payload = mutate.mock.calls[0][0];
    expect(payload.plate_format).toBeUndefined();
    expect(JSON.parse(JSON.stringify(payload))).not.toHaveProperty("plate_format");
    expect(payload.plate_template_id).toBeNull();
  });
});
