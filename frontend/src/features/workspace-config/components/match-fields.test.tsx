import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

beforeAll(() => {
  Element.prototype.scrollIntoView ??= vi.fn();
  Element.prototype.hasPointerCapture ??= vi.fn(() => false);
  Element.prototype.releasePointerCapture ??= vi.fn();
});

const api = vi.hoisted(() => ({ calls: [] as { url: string; method: string; data?: unknown }[] }));
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: async (cfg: { url: string; method: string; data?: { headers: string[] } }) => {
    api.calls.push(cfg);
    if (cfg.url.endsWith("/vault-fields")) {
      return {
        molecule: [
          { path: "name", label: "Name" },
          { path: "synonyms", label: "Alternate Names" },
        ],
        batch: [
          { path: "batch.name", label: "Batch Name" },
          { path: "batch.legacy", label: "LGCY Batch Name" },
        ],
      };
    }
    if (cfg.url.endsWith("/suggest-mapping")) {
      return {
        columns: cfg.data?.headers.map((h) => ({
          header: h,
          target: h === "Alternate Names" ? "compound_id" : h === "Name" ? "name" : "ignore",
          source: h === "Alternate Names" ? "Alternate Names" : null,
        })),
      };
    }
    return {};
  },
}));
vi.mock("@/shared/lib/toast", () => ({ showSuccess: vi.fn(), showError: vi.fn() }));

import { MatchFields } from "./match-fields";

function renderIt(saved: Parameters<typeof MatchFields>[0]["saved"] = null) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MatchFields dataSourceId="ds-1" saved={saved} />
    </QueryClientProvider>,
  );
}
const goesTo = (label: string) => screen.findByRole("combobox", { name: `Where ${label} goes` });

beforeEach(() => {
  api.calls.length = 0;
});

describe("MatchFields", () => {
  it("shows Molecule and Batch groups, suggests Compound ID for Alternate Names, leaves LGCY unmapped", async () => {
    renderIt();
    expect(await screen.findByText("Molecule fields")).toBeInTheDocument();
    expect(screen.getByText("Batch fields")).toBeInTheDocument();
    expect(await goesTo("Alternate Names")).toHaveTextContent("Compound ID");
    expect(await goesTo("LGCY Batch Name")).toHaveTextContent("Don't import");
  });

  it("offers compound targets to molecule rows and batch targets to batch rows", async () => {
    renderIt();
    fireEvent.keyDown(await goesTo("Name"), { key: "Enter" });
    expect(screen.getByRole("option", { name: "CAS number" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Purity (%)" })).not.toBeInTheDocument();
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
  });

  it("a saved entry wins over the suggestion, and Save sends the PATCH body with ;", async () => {
    renderIt([{ header: "synonyms", target: "ignore", source: null }]);
    expect(await goesTo("Alternate Names")).toHaveTextContent("Don't import");
    fireEvent.keyDown(await goesTo("LGCY Batch Name"), { key: "Enter" });
    fireEvent.click(screen.getByRole("option", { name: "Batch ID" }));
    const box = await screen.findByRole("checkbox", {
      name: "Several values, separated by ; (LGCY Batch Name)",
    });
    fireEvent.click(box);
    fireEvent.click(screen.getByRole("button", { name: "Save field matching" }));
    await waitFor(() => expect(api.calls.some((c) => c.method === "PATCH")).toBe(true));
    const patch = api.calls.find((c) => c.method === "PATCH");
    const cols = (patch?.data as { registration_mapping: { header: string }[] })
      .registration_mapping;
    expect(patch?.url).toBe("/api/v1/data-sources/ds-1");
    expect(cols.find((c) => c.header === "batch.legacy")).toMatchObject({
      target: "batch_id",
      source: "LGCY Batch Name",
      separator: ";",
    });
    expect(within(document.body).queryByText("Saving...")).toBeNull();
  });
});
