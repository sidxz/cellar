import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const targets = [
  {
    id: "t-1",
    workspace_id: "ws",
    name: "NadD",
    target_type: "single_protein",
    organism: "Mycobacterium tuberculosis",
    chembl_id: "CHEMBL4630874",
    gene_name: null,
    uniprot_id: null,
    ncbi_gene_id: null,
    description: null,
    target_class: null,
  },
];

let syncResult: () => Promise<unknown> = async () => ({
  fetched: 126,
  created: 3,
  updated: 1,
  skipped: 122,
});

const customInstance = vi.fn(async (args: { url: string; method: string }) => {
  if (args.url === "/api/v1/targets" && args.method === "GET") {
    return { items: targets, next_cursor: null };
  }
  if (args.url === "/api/v1/targets/sync" && args.method === "POST") return syncResult();
  throw new Error(`unexpected ${args.method} ${args.url}`);
});
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: (args: unknown) => customInstance(args as never),
}));

import { AdminTargetsPage } from "./admin-targets-page";

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return render(<AdminTargetsPage />, { wrapper });
}

describe("AdminTargetsPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("lists mirrored targets read-only with a prot-cellar deep link", async () => {
    renderPage();
    expect(await screen.findByText("NadD")).toBeInTheDocument();
    expect(screen.getByText("Mycobacterium tuberculosis")).toBeInTheDocument();
    expect(screen.getByText("CHEMBL4630874")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /open nadd in prot-cellar/i });
    expect(link).toHaveAttribute("href", "http://localhost:3001/targets/t-1");
    expect(screen.queryByRole("button", { name: /delete|edit/i })).not.toBeInTheDocument();
  });

  it("sync button reports counts on success", async () => {
    renderPage();
    await screen.findByText("NadD");
    fireEvent.click(screen.getByRole("button", { name: /sync from prot-cellar/i }));
    await waitFor(() => expect(screen.getByText(/126 fetched/i)).toBeInTheDocument());
    expect(screen.getByText(/3 created · 1 updated · 122 unchanged/i)).toBeInTheDocument();
  });

  it("sync button surfaces the backend error message", async () => {
    syncResult = async () => {
      // Mirrors custom-instance.ts's detail rule (a string `body.detail` becomes
      // `API error: <status> — <detail>`) rather than hand-writing the message,
      // so this test breaks if that coupling ever drifts.
      const body = {
        error: "AuthorizationError",
        message: "prot-cellar refused the request: editor role required",
        detail: "(403) editor required. Target reads in prot-cellar require the editor role.",
      };
      throw new Error(`API error: 403 — ${body.detail}`);
    };
    renderPage();
    await screen.findByText("NadD");
    fireEvent.click(screen.getByRole("button", { name: /sync from prot-cellar/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/editor required/i);
  });
});
