import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render as rtlRender, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Protocol } from "../types";
import { ProtocolDetail } from "./protocol-detail";

const state = vi.hoisted(() => ({ protocol: null as unknown, canCreate: true }));

vi.mock("@duar-auth/nextjs", () => ({
  useAuthzHasRole: (role: string) => role === "editor" && state.canCreate,
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/assays/protocols/p1",
}));
vi.mock("@/shared/hooks/use-hash-tab", () => ({ useHashTab: () => ["overview", vi.fn()] }));
vi.mock("../hooks/use-protocol-name-preview", () => ({
  useProtocolNamePreview: () => ({ data: null }),
}));
vi.mock("../hooks/use-protocols", () => {
  const mutation = () => ({ mutate: vi.fn(), isPending: false });
  return {
    useProtocol: () => ({ data: state.protocol, isLoading: false }),
    usePublishProtocol: mutation,
    useRetireProtocol: mutation,
    useVersionProtocol: mutation,
    useUpdateProtocol: mutation,
    useDeleteProtocol: mutation,
    useLockProtocol: mutation,
    useUnlockProtocol: mutation,
  };
});
vi.mock("./detail-tabs", () => ({
  ActivityTab: () => null,
  DesignTab: () => null,
  FilesTab: () => null,
  OverviewTab: () => null,
  RunsTab: () => null,
}));
vi.mock("./correct-protocol-dialog", () => ({ CorrectProtocolDialog: () => null }));
vi.mock("./create-run-dialog", () => ({ CreateRunDialog: () => null }));
vi.mock("./protocol-category-input", () => ({ ProtocolCategoryInput: () => null }));
// The dialog's own prefill is tested in create-protocol-dialog.test.tsx.
vi.mock("./create-protocol-dialog", () => ({
  CreateProtocolDialog: ({ open, prefill }: { open: boolean; prefill?: Protocol }) =>
    open && prefill ? <div>New protocol from {prefill.code}</div> : null,
}));

const render = () =>
  rtlRender(
    <QueryClientProvider client={new QueryClient()}>
      <ProtocolDetail protocolId="p1" />
    </QueryClientProvider>,
  );

const protocol = (over: Partial<Protocol> = {}) =>
  ({
    id: "p1",
    code: "PRT-00001",
    name: "PptT inhibition",
    status: "draft",
    is_locked: false,
    can_delete: false,
    targets: [],
    aliases: [],
    readout_definitions: [],
    condition_definitions: [],
    ...over,
  }) as unknown as Protocol;

const openMore = () => {
  const more = screen.getByRole("button", { name: /More/ });
  fireEvent.keyDown(more, { key: "Enter" });
};

describe("ProtocolDetail actions", () => {
  beforeEach(() => {
    state.canCreate = true;
    state.protocol = protocol();
  });

  it("has no Duplicate on a draft; New protocol from this takes its place", () => {
    render();
    openMore();
    expect(screen.queryByRole("menuitem", { name: "Duplicate" })).not.toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "New protocol from this" })).toBeInTheDocument();
  });

  it.each(["draft", "active", "retired"])(
    "offers New protocol from this on a %s protocol",
    (status) => {
      state.protocol = protocol({ status } as Partial<Protocol>);
      render();
      openMore();
      expect(screen.getByRole("menuitem", { name: "New protocol from this" })).toBeInTheDocument();
    },
  );

  it("keeps New Version on an active protocol", () => {
    state.protocol = protocol({ status: "active" } as Partial<Protocol>);
    render();
    openMore();
    expect(screen.getByRole("menuitem", { name: "New Version" })).toBeInTheDocument();
  });

  it("opens the create dialog prefilled from this protocol", () => {
    render();
    openMore();
    fireEvent.click(screen.getByRole("menuitem", { name: "New protocol from this" }));
    expect(screen.getByText("New protocol from PRT-00001")).toBeInTheDocument();
  });

  it("hides it from roles that cannot create protocols", () => {
    state.canCreate = false;
    render();
    openMore();
    expect(
      screen.queryByRole("menuitem", { name: "New protocol from this" }),
    ).not.toBeInTheDocument();
  });
});
