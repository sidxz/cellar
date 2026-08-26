import { customInstance } from "@/shared/lib/api/custom-instance";
import type { PlateData } from "@/shared/lib/api/model";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { RunPlateLink } from "./run-plate-link";

vi.mock("@/shared/lib/api/custom-instance", () => ({ API_V1: "/api/v1", customInstance: vi.fn() }));
vi.mock("@/shared/lib/toast", () => ({ showSuccess: vi.fn(), showError: vi.fn() }));
const mocked = vi.mocked(customInstance);

beforeAll(() => {
  // Radix dialogs in jsdom (verbatim from request-loan-dialog.test.tsx).
  if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = vi.fn();
  if (!Element.prototype.hasPointerCapture)
    Element.prototype.hasPointerCapture = vi.fn(() => false);
  if (!Element.prototype.releasePointerCapture) Element.prototype.releasePointerCapture = vi.fn();
});

const unlinked: PlateData = {
  plate_id: "pl1",
  plate_number: 1,
  format: "384",
  wells: [],
  summary: {
    total_wells: 0,
    sample_wells: 0,
    control_wells: 0,
    compounds: 0,
    concentrations_per_compound: 0,
    replicates: 0,
  },
  registered_plate_id: null,
  registered_plate_barcode: null,
  registered_plate_label: null,
};
const linked: PlateData = {
  ...unlinked,
  registered_plate_id: "rp1",
  registered_plate_barcode: "003070",
  registered_plate_label: "SAC3-014-3070",
};

function setup(plate: PlateData, readOnly?: boolean) {
  mocked.mockReset();
  mocked.mockResolvedValue({ plate_id: "pl1" });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(<RunPlateLink runId="r1" plate={plate} readOnly={readOnly} />, { wrapper });
}

describe("RunPlateLink", () => {
  it("linked: barcode links to the inventory plate; Unlink posts :unlink", async () => {
    setup(linked);
    expect(screen.getByRole("link", { name: "003070" })).toHaveAttribute(
      "href",
      "/inventory/plates/rp1",
    );
    expect(screen.getByText("SAC3-014-3070")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Unlink" }));
    await waitFor(() =>
      expect(mocked).toHaveBeenCalledWith(
        expect.objectContaining({ url: "/api/v1/runs/r1/plates/pl1:unlink", method: "POST" }),
      ),
    );
  });

  it("unlinked: Link plate opens a dialog; submitting posts :link with the typed value", async () => {
    setup(unlinked);
    fireEvent.click(screen.getByRole("button", { name: "Link plate" }));
    const input = await screen.findByLabelText("Barcode or plate name");
    fireEvent.change(input, { target: { value: " SAC3-014-3070 " } });
    fireEvent.click(screen.getByRole("button", { name: "Link" }));
    await waitFor(() =>
      expect(mocked).toHaveBeenCalledWith(
        expect.objectContaining({
          url: "/api/v1/runs/r1/plates/pl1:link",
          method: "POST",
          data: { barcode: "SAC3-014-3070" },
        }),
      ),
    );
  });

  it("readOnly: link stays, no Unlink; nothing at all when unlinked", () => {
    setup(linked, true);
    expect(screen.getByRole("link", { name: "003070" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Unlink" })).not.toBeInTheDocument();

    const { container } = setup(unlinked, true);
    expect(screen.queryByRole("button", { name: "Link plate" })).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });
});
