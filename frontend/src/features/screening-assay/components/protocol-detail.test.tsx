import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render as rtlRender, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Protocol } from "../types";
import { ProtocolDetail } from "./protocol-detail";

const state = vi.hoisted(() => ({ protocol: null as unknown, canCreate: true, hash: "" }));

vi.mock("@duar-auth/nextjs", () => ({
  useAuthzHasRole: (role: string) => role === "editor" && state.canCreate,
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/assays/protocols/p1",
}));
vi.mock("@/shared/hooks/use-hash-tab", async () => {
  const { useState } = await import("react");
  return { useHashTab: (fallback: string) => useState(state.hash || fallback) };
});
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
  ActivityTab: () => <input aria-label="Filter compound activity" />,
  DesignTab: () => <div>Readout setup</div>,
  FilesTab: () => null,
  OverviewTab: () => <div>Overview content</div>,
  RunsTab: ({ onCompareCurves }: { onCompareCurves: (ids: string[]) => void }) => (
    <button type="button" onClick={() => onCompareCurves(["r1", "r3"])}>
      Compare traces
    </button>
  ),
  CurvesTab: ({ runIds }: { runIds: readonly string[] }) => (
    <div>Curves for {runIds.join(",") || "none"}</div>
  ),
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
    state.hash = "";
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

  it("keeps workflow actions in the header and Visualize in Results", () => {
    state.protocol = protocol({ status: "active" } as Partial<Protocol>);
    render();
    expect(screen.getByRole("button", { name: "New Run" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Visualize" })).not.toBeInTheDocument();
    selectTab("Results");
    const visualize = screen.getByRole("button", { name: "Visualize" }).parentElement;
    expect(visualize).toContainElement(screen.getByRole("button", { name: "Saved views" }));
  });
});

function selectTab(name: string) {
  fireEvent.mouseDown(screen.getByRole("tab", { name }), {
    button: 0,
    ctrlKey: false,
  });
}

describe("ProtocolDetail navigation", () => {
  beforeEach(() => {
    state.canCreate = true;
    state.hash = "";
    state.protocol = protocol();
  });

  it("has five main sections with the setup workspace on Setup", () => {
    render();
    expect(screen.getByRole("tablist", { name: "Protocol sections" })).toHaveTextContent(
      "OverviewRunsResultsSetupFiles",
    );
    expect(screen.queryByText("Readout setup")).not.toBeInTheDocument();
    selectTab("Setup");
    expect(screen.getByText("Readout setup")).toBeVisible();
  });

  it.each([
    ["design", "Setup", "Readout setup"],
    ["activity", "Results", null],
  ])("keeps legacy #%s links working", (hash, section, content) => {
    state.hash = hash;
    render();
    expect(screen.getByRole("tab", { name: section })).toHaveAttribute("aria-selected", "true");
    if (content) expect(screen.getByText(content)).toBeVisible();
    else expect(screen.getByRole("textbox", { name: "Filter compound activity" })).toBeVisible();
  });

  it("retains compound filters when navigating to Runs and back", () => {
    render();
    selectTab("Results");
    fireEvent.change(screen.getByRole("textbox", { name: "Filter compound activity" }), {
      target: { value: "CC-061341" },
    });
    selectTab("Runs");
    selectTab("Results");
    expect(screen.getByRole("textbox", { name: "Filter compound activity" })).toHaveValue(
      "CC-061341",
    );
  });

  it("offers trace comparison inside Results only when the protocol has measured curves", () => {
    for (const has_measured_curves of [false, null, undefined]) {
      state.protocol = protocol({ has_measured_curves } as Partial<Protocol>);
      const { unmount } = render();
      selectTab("Results");
      expect(screen.queryByRole("tab", { name: "Compare traces" })).not.toBeInTheDocument();
      unmount();
    }
    state.protocol = protocol({ has_measured_curves: true } as Partial<Protocol>);
    render();
    selectTab("Results");
    expect(screen.getByRole("tab", { name: "Compare traces" })).toBeInTheDocument();
  });

  it("shows the overview for a curves link on a protocol without measured curves", () => {
    state.hash = "curves";
    state.protocol = protocol({ has_measured_curves: false } as Partial<Protocol>);
    render();
    expect(screen.getByText("Overview content")).toBeVisible();
  });

  it("opens trace comparison from its existing link", () => {
    state.hash = "curves";
    state.protocol = protocol({ has_measured_curves: true } as Partial<Protocol>);
    render();
    expect(screen.getByRole("tab", { name: "Results" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Compare traces" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByText("Curves for none")).toBeVisible();
  });

  it("compares runs selected in Runs and retains them after switching sections", () => {
    state.hash = "runs";
    state.protocol = protocol({ has_measured_curves: true } as Partial<Protocol>);
    render();
    fireEvent.click(screen.getByRole("button", { name: "Compare traces" }));
    expect(screen.getByRole("tab", { name: "Results" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Compare traces" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByText("Curves for r1,r3")).toBeVisible();
    selectTab("Files");
    selectTab("Results");
    expect(screen.getByRole("tab", { name: "Compare traces" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByText("Curves for r1,r3")).toBeVisible();
  });
});
