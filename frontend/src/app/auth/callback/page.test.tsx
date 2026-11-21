import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { rememberPlace } from "@/shared/lib/auth/return-after-login";
import CallbackPage from "./page";

const state = vi.hoisted(() => ({ replace: vi.fn(), returnTo: null as string | null }));
afterEach(() => {
  state.replace.mockReset();
  state.returnTo = null;
  window.sessionStorage.clear();
});

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: state.replace }) }));
vi.mock("@/shared/components/login-plate/login-plate", () => ({ LoginPlate: () => null }));
vi.mock("./workspace-selector", () => ({ WorkspaceSelector: () => null }));
// Sign-in has just succeeded: the callback reports it straight away.
vi.mock("@duar-auth/nextjs", () => ({
  AuthzCallback: ({
    onSuccess,
  }: { onSuccess: (user: unknown, returnTo: string | null) => void }) => {
    onSuccess({}, state.returnTo);
    return null;
  },
}));

describe("the sign-in callback", () => {
  it("returns to the page the visitor asked for", () => {
    rememberPlace("/assays?new_protocol=1&return_to=x");
    render(<CallbackPage />);
    expect(state.replace).toHaveBeenCalledWith("/assays?new_protocol=1&return_to=x");
  });

  it("prefers the place a silent re-auth recorded", () => {
    rememberPlace("/assays");
    state.returnTo = "/compounds";
    render(<CallbackPage />);
    expect(state.replace).toHaveBeenCalledWith("/compounds");
  });

  it("goes home when nothing was asked for", () => {
    render(<CallbackPage />);
    expect(state.replace).toHaveBeenCalledWith("/");
  });
});
