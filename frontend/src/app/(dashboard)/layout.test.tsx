import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { takePlace } from "@/shared/lib/auth/return-after-login";
import DashboardLayout from "./layout";

const state = vi.hoisted(() => ({ replace: vi.fn(), authState: "unauthenticated" }));
afterEach(() => {
  state.replace.mockReset();
  state.authState = "unauthenticated";
  window.sessionStorage.clear();
  window.history.replaceState(null, "", "/");
});

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: state.replace }) }));
vi.mock("@duar-auth/nextjs", () => ({
  useAuthz: () => ({ authState: state.authState, isLoading: false }),
}));
vi.mock("@/shared/hooks/use-preferences-sync", () => ({ usePreferencesSync: () => {} }));
vi.mock("@/shared/components/layout/app-sidebar", () => ({ AppSidebar: () => null }));
vi.mock("@/shared/components/layout/header", () => ({ Header: () => null }));
vi.mock("@/shared/components/ui/sidebar", () => ({
  SidebarProvider: ({ children }: { children: React.ReactNode }) => children,
  SidebarInset: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("@/shared/components/layout/route-access", () => ({
  RouteAccess: ({ children }: { children: React.ReactNode }) => children,
}));

describe("the dashboard for a signed-out visitor", () => {
  it("remembers the page asked for before sending them to sign in", () => {
    window.history.replaceState(null, "", "/assays?new_protocol=1&return_to=x");
    render(
      <DashboardLayout>
        <div />
      </DashboardLayout>,
    );
    expect(state.replace).toHaveBeenCalledWith("/login");
    expect(takePlace()).toBe("/assays?new_protocol=1&return_to=x");
  });

  it("does not remember the page after signing out on purpose", () => {
    window.history.replaceState(null, "", "/assays/protocols/p1");
    state.authState = "authenticated";
    // A fresh element each time, so the layout re-renders and reads the new auth state.
    const page = () => (
      <DashboardLayout>
        <div />
      </DashboardLayout>
    );
    const { rerender } = render(page());
    // Sign out or Switch workspace: the session ends while the page is open.
    state.authState = "unauthenticated";
    rerender(page());
    expect(state.replace).toHaveBeenCalledWith("/login");
    expect(takePlace()).toBeNull();
  });
});
