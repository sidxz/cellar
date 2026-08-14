import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

const orgs = [{ id: "org-1", slug: "org-1", name: "Org One" }];

const devices = [
  {
    id: "dev-1",
    org_id: "org-1",
    name: "Bench Scanner",
    is_active: true,
    last_seen_at: null,
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "dev-2",
    org_id: "org-1",
    name: "Old Scanner",
    is_active: false,
    last_seen_at: "2026-02-01T00:00:00Z",
    created_at: "2026-01-01T00:00:00Z",
  },
];

const ISSUED_TOKEN = "tok_abc123xyz";

// Radix Select opens via a listbox portal that calls scrollIntoView +
// hasPointerCapture on its items — jsdom ships neither. Polyfill so the
// open/click flow works under test (verbatim from org-plate-policy-dialog.test.tsx).
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
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText: vi.fn(() => Promise.resolve()) },
    configurable: true,
  });
});

const customInstance = vi.fn(async (args: { url: string; method: string; data?: unknown }) => {
  if (args.url === "/api/v1/orgs") return orgs;
  if (args.url === "/api/v1/kiosk-devices" && args.method === "GET") return devices;
  if (args.url === "/api/v1/kiosk-devices" && args.method === "POST") {
    const body = args.data as { name: string; org_id: string };
    return {
      id: "dev-new",
      org_id: body.org_id,
      name: body.name,
      is_active: true,
      last_seen_at: null,
      created_at: "2026-03-01T00:00:00Z",
      token: ISSUED_TOKEN,
    };
  }
  if (args.url === "/api/v1/kiosk-devices/dev-1:revoke" && args.method === "POST") {
    return { ...devices[0], is_active: false };
  }
  throw new Error(`unexpected ${args.method} ${args.url}`);
});
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: (args: unknown) => customInstance(args as never),
}));

const showSuccess = vi.fn();
const showError = vi.fn();
vi.mock("@/shared/lib/toast", () => ({
  showSuccess: (...args: unknown[]) => showSuccess(...args),
  showError: (...args: unknown[]) => showError(...args),
}));

import { KioskDeviceAdmin } from "./kiosk-device-admin";

function renderAdmin() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return render(<KioskDeviceAdmin />, { wrapper });
}

describe("KioskDeviceAdmin", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders device rows with org name, 'Never' last-seen, and hides Revoke for revoked rows", async () => {
    renderAdmin();

    expect(await screen.findByText("Bench Scanner")).toBeInTheDocument();
    expect(screen.getAllByText("Org One")).toHaveLength(2);
    expect(screen.getByText("Never")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Revoked")).toBeInTheDocument();

    // dev-2 is already revoked — its row must not offer a Revoke action.
    expect(screen.getAllByRole("button", { name: /^revoke$/i })).toHaveLength(1);
  });

  it("creates a device, reveals its token exactly once, and supports copy", async () => {
    renderAdmin();
    await screen.findByText("Bench Scanner");

    fireEvent.click(screen.getByRole("button", { name: /add device/i }));

    fireEvent.change(await screen.findByLabelText(/name/i), {
      target: { value: "New Scanner" },
    });
    fireEvent.click(screen.getByRole("combobox"));
    fireEvent.click(await screen.findByRole("option", { name: "Org One" }));
    fireEvent.click(screen.getByRole("button", { name: /^create$/i }));

    await waitFor(() =>
      expect(customInstance).toHaveBeenCalledWith(
        expect.objectContaining({
          url: "/api/v1/kiosk-devices",
          method: "POST",
          data: { name: "New Scanner", org_id: "org-1" },
        }),
      ),
    );

    // Create dialog is gone, token-reveal dialog is up with the minted token.
    expect(screen.queryByRole("button", { name: /^create$/i })).not.toBeInTheDocument();
    const tokenEl = await screen.findByTestId("kiosk-token");
    expect(tokenEl).toHaveTextContent(ISSUED_TOKEN);

    fireEvent.click(screen.getByRole("button", { name: /copy/i }));
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith(ISSUED_TOKEN));
    expect(showSuccess).toHaveBeenCalledWith("Token copied");

    // Done discards the token from state — it is not re-shown.
    fireEvent.click(screen.getByRole("button", { name: /^done$/i }));
    await waitFor(() => expect(screen.queryByTestId("kiosk-token")).not.toBeInTheDocument());
  });

  it("revoke confirm POSTs the colon-verb endpoint", async () => {
    renderAdmin();
    await screen.findByText("Bench Scanner");

    fireEvent.click(screen.getByRole("button", { name: /^revoke$/i }));

    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^revoke$/i }));

    await waitFor(() =>
      expect(customInstance).toHaveBeenCalledWith(
        expect.objectContaining({
          url: "/api/v1/kiosk-devices/dev-1:revoke",
          method: "POST",
        }),
      ),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});
