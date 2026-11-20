import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { takePlace } from "@/shared/lib/auth/return-after-login";
import DashboardLayout from "./layout";

const state = vi.hoisted(() => ({ replace: vi.fn() }));
afterEach(() => {
  state.replace.mockReset();
  window.sessionStorage.clear();
  window.history.replaceState(null, "", "/");
});

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: state.replace }) }));
vi.mock("@duar-auth/nextjs", () => ({
  useAuthz: () => ({ authState: "unauthenticated", isLoading: false }),
}));
vi.mock("@/shared/hooks/use-preferences-sync", () => ({ usePreferencesSync: () => {} }));
vi.mock("@/shared/components/layout/app-sidebar", () => ({ AppSidebar: () => null }));
vi.mock("@/shared/components/layout/header", () => ({ Header: () => null }));
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
});
