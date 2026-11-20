import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { type AppConfig, AppConfigProvider } from "@/shared/lib/app-config";
import { ScreeningDashboard } from "./screening-dashboard";

type DialogProps = {
  start?: { category: string | null };
  returnTarget?: { label: string; url: string } | null;
  onOpenChange: (open: boolean) => void;
};
const state = vi.hoisted(() => ({
  params: new URLSearchParams(),
  replace: vi.fn(),
  linkDialog: null as DialogProps | null,
}));
afterEach(() => {
  state.params = new URLSearchParams();
  state.replace.mockReset();
  state.linkDialog = null;
});

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: state.replace }),
  useSearchParams: () => state.params,
  usePathname: () => "/assays",
}));
vi.mock("@duar-auth/nextjs", () => ({ useAuthzHasRole: () => true }));
vi.mock("../hooks/use-cdd-enabled", () => ({ useCddEnabled: () => ({ enabled: false }) }));
vi.mock("@/features/workspace-config/components/setup-checklist", () => ({
  SetupChecklist: () => null,
}));
vi.mock("./protocol-browser", () => ({ ProtocolBrowser: () => null }));
vi.mock("./cdd-import-dialog", () => ({ CddImportDialog: () => null }));
vi.mock("./create-run-dialog", () => ({ CreateRunDialog: () => null }));
vi.mock("./protocol-csv-import/protocol-csv-import-dialog", () => ({
  ProtocolCsvImportDialog: () => null,
}));
vi.mock("./create-protocol-dialog", () => ({
  CreateProtocolDialog: (props: DialogProps) => {
    if (!props.start) return null;
    state.linkDialog = props;
    return <div data-testid="link-dialog" />;
  },
}));

const config = { returnOrigins: [{ label: "Daikon", origin: "https://d.org" }] } as AppConfig;
const visit = (query: string) => {
  state.params = new URLSearchParams(query);
  return render(
    <AppConfigProvider config={config}>
      <ScreeningDashboard />
    </AppConfigProvider>,
  );
};

describe("ScreeningDashboard opened from a link", () => {
  it("opens New protocol with the link's start and the trusted way back", async () => {
    visit("new_protocol=1&category=Cytotoxicity&return_to=https%3A%2F%2Fd.org%2Fs");
    expect(await screen.findByTestId("link-dialog")).toBeInTheDocument();
    expect(state.linkDialog?.start?.category).toBe("Cytotoxicity");
    expect(state.linkDialog?.returnTarget).toEqual({ label: "Daikon", url: "https://d.org/s" });
  });

  it("closing it keeps only return_to in the address", async () => {
    visit("new_protocol=1&category=Cytotoxicity&return_to=https%3A%2F%2Fd.org%2Fs");
    await screen.findByTestId("link-dialog");
    state.linkDialog?.onOpenChange(false);
    expect(state.replace).toHaveBeenCalledWith("/assays?return_to=https%3A%2F%2Fd.org%2Fs");
  });

  it("opens nothing for a plain visit", () => {
    visit("");
    expect(screen.queryByTestId("link-dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /New protocol/ })).toBeInTheDocument();
  });
});
