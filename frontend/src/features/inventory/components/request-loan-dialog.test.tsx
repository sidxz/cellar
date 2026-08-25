import { customInstance } from "@/shared/lib/api/custom-instance";
import { saveText } from "@/shared/lib/api/download";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { RequestLoanDialog } from "./request-loan-dialog";

vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: vi.fn(),
}));
vi.mock("@/shared/lib/toast", () => ({
  showSuccess: vi.fn(),
  showError: vi.fn(),
}));
vi.mock("@/shared/lib/api/download", () => ({
  saveText: vi.fn(),
}));

const mocked = vi.mocked(customInstance);
const mockedSaveText = vi.mocked(saveText);

// Radix Select/Tabs open via a portal that calls scrollIntoView +
// hasPointerCapture on its items — jsdom ships neither. Polyfill so the
// open/click flow works under test (verbatim from plate-group-dialog.test.tsx).
beforeAll(() => {
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = vi.fn();
  }
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = vi.fn(() => false);
  }
  if (!Element.prototype.releasePointerCapture) {
    Element.prototype.releasePointerCapture = vi.fn();
  }
});

function setup() {
  mocked.mockReset();
  mockedSaveText.mockReset();
  mocked.mockImplementation((opts: { url: string; method: string }) => {
    if (opts.url === "/api/v1/orgs") {
      return Promise.resolve([
        { id: "org1", slug: "org1", name: "Org One" },
        { id: "org2", slug: "org2", name: "Org Two" },
      ]);
    }
    if (opts.method === "GET") return Promise.resolve({ roots: [] }); // group tree
    return Promise.resolve({ id: "loan1", items: [] }); // POST request-loan
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(<RequestLoanDialog open onOpenChange={() => {}} orgId="org1" />, { wrapper });
}

describe("RequestLoanDialog", () => {
  it("submit is disabled until the active mode has input", () => {
    setup();
    // Defaults to From-group mode with an empty tree — nothing selectable yet.
    expect(screen.getByRole("button", { name: /request loan/i })).toBeDisabled();
  });

  it("paste mode POSTs a barcodes body, one per line", async () => {
    setup();
    fireEvent.mouseDown(screen.getByRole("tab", { name: /paste/i }));
    fireEvent.change(screen.getByPlaceholderText(/one barcode per line/i), {
      target: { value: "005261\n5261\n" },
    });
    fireEvent.click(screen.getByRole("button", { name: /request loan/i }));
    await waitFor(() =>
      expect(mocked).toHaveBeenCalledWith(
        expect.objectContaining({
          url: "/api/v1/plate-loans",
          method: "POST",
          data: expect.objectContaining({ barcodes: ["005261", "5261"] }),
        }),
      ),
    );
  });

  it("sends borrower_org_id only when a foreign org is selected, and the button reads Lend", async () => {
    setup();
    fireEvent.mouseDown(screen.getByRole("tab", { name: /paste/i }));
    fireEvent.change(screen.getByPlaceholderText(/one barcode per line/i), {
      target: { value: "005261\n" },
    });

    // Default: self-checkout — no borrower_org_id, button reads "Request loan".
    fireEvent.click(screen.getByRole("button", { name: /request loan/i }));
    await waitFor(() => expect(mocked).toHaveBeenCalled());
    const defaultCall = mocked.mock.calls.find(
      ([opts]) => (opts as { url: string }).url === "/api/v1/plate-loans",
    );
    expect(defaultCall?.[0]).not.toHaveProperty("data.borrower_org_id");

    // Pick a foreign org — borrower_org_id is sent, button reads "Lend".
    fireEvent.click(await screen.findByLabelText(/borrower organization/i));
    fireEvent.click(await screen.findByRole("option", { name: "Org Two" }));
    const lendButton = screen.getByRole("button", { name: "Lend" });
    fireEvent.click(lendButton);
    await waitFor(() => {
      const lendCall = mocked.mock.calls
        .filter(([opts]) => (opts as { url: string }).url === "/api/v1/plate-loans")
        .at(-1);
      expect(lendCall?.[0]).toEqual(
        expect.objectContaining({ data: expect.objectContaining({ borrower_org_id: "org2" }) }),
      );
    });
  });

  it("download-template button saves a Barcode-headed CSV", () => {
    setup();
    fireEvent.mouseDown(screen.getByRole("tab", { name: /csv/i }));
    fireEvent.click(screen.getByRole("button", { name: /template/i }));
    expect(mockedSaveText).toHaveBeenCalledWith(
      expect.stringMatching(/^Barcode/),
      "loan_request_template.csv",
    );
  });

  it("csv mode parses the uploaded file's first column and POSTs it", async () => {
    setup();
    fireEvent.mouseDown(screen.getByRole("tab", { name: /csv/i }));
    const file = new File(["Barcode\n005261\n003251\n"], "plates.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText(/csv file/i), { target: { files: [file] } });
    const submit = screen.getByRole("button", { name: /request loan/i });
    await waitFor(() => expect(submit).not.toBeDisabled());
    fireEvent.click(submit);
    await waitFor(() =>
      expect(mocked).toHaveBeenCalledWith(
        expect.objectContaining({
          url: "/api/v1/plate-loans",
          method: "POST",
          data: expect.objectContaining({ barcodes: ["005261", "003251"] }),
        }),
      ),
    );
  });
});
