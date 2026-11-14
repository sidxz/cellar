import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Protocol } from "../../types";
import { ProtocolMethodCard } from "./protocol-method-card";

const state = vi.hoisted(() => ({
  editor: true,
  update: vi.fn(),
  correct: vi.fn(),
}));
afterEach(() => {
  state.editor = true;
  state.update.mockReset();
  state.correct.mockReset();
});

vi.mock("@duar-auth/nextjs", () => ({ useAuthzHasRole: () => state.editor }));
vi.mock("../../hooks/use-protocols", () => ({
  useUpdateProtocol: () => ({ mutate: state.update, isPending: false }),
  useCorrectProtocol: () => ({ mutate: state.correct, isPending: false }),
}));

const METHOD = "Materials: InhA 50 nM\nProcedure:\n1. Preincubate 10 min\n2. Read A340";

function protocol(overrides: Partial<Protocol> = {}): Protocol {
  return {
    id: "p-1",
    status: "draft",
    is_locked: false,
    description: METHOD,
    ...overrides,
  } as Protocol;
}

const card = (p: Protocol, onOpenFiles = vi.fn()) =>
  render(<ProtocolMethodCard protocol={p} onOpenFiles={onOpenFiles} />);

describe("ProtocolMethodCard", () => {
  it("shows the method with its line breaks", () => {
    card(protocol());
    const text = screen.getByText(/Preincubate 10 min/);
    expect(text.textContent).toBe(METHOD);
    expect(text).toHaveClass("whitespace-pre-wrap");
  });

  it("saves a draft's method without asking for a reason", () => {
    card(protocol());
    fireEvent.click(screen.getByRole("button", { name: "Edit method" }));
    expect(screen.queryByLabelText("Reason for the change")).not.toBeInTheDocument();
    const save = screen.getByRole("button", { name: "Save" });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Method"), { target: { value: `${METHOD}\n3. Fit` } });
    fireEvent.click(save);
    expect(state.update).toHaveBeenCalledWith(
      { description: `${METHOD}\n3. Fit` },
      expect.anything(),
    );
    expect(state.correct).not.toHaveBeenCalled();
  });

  it("corrects a published method only with a reason", () => {
    card(protocol({ status: "active" }));
    fireEvent.click(screen.getByRole("button", { name: "Edit method" }));
    fireEvent.change(screen.getByLabelText("Method"), { target: { value: "Fixed" } });
    const save = screen.getByRole("button", { name: "Save" });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Reason for the change"), {
      target: { value: "Typo" },
    });
    fireEvent.click(save);
    expect(state.correct).toHaveBeenCalledWith(
      { reason: "Typo", description: "Fixed" },
      expect.anything(),
    );
    expect(state.update).not.toHaveBeenCalled();
  });

  it("cancel discards the edit", () => {
    card(protocol());
    fireEvent.click(screen.getByRole("button", { name: "Edit method" }));
    fireEvent.change(screen.getByLabelText("Method"), { target: { value: "Changed" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByText(/Preincubate 10 min/)).toBeInTheDocument();
    expect(state.update).not.toHaveBeenCalled();
  });

  it.each([
    ["locked", protocol({ status: "active", is_locked: true })],
    ["retired", protocol({ status: "retired" })],
  ])("is read-only when %s", (_label, p) => {
    card(p);
    expect(screen.getByText(/Preincubate 10 min/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit method" })).not.toBeInTheDocument();
  });

  it("is read-only for a viewer, and says when nothing is recorded", () => {
    state.editor = false;
    card(protocol({ description: null }));
    expect(screen.getByText("No method recorded.")).toBeInTheDocument();
  });

  it("invites an editor to add a missing method", () => {
    card(protocol({ description: null }));
    fireEvent.click(screen.getByRole("button", { name: /Add the method/ }));
    expect(screen.getByLabelText("Method")).toHaveValue("");
  });

  it("clamps a long method behind Show all", () => {
    const long = Array.from({ length: 20 }, (_, i) => `${i + 1}. step`).join("\n");
    card(protocol({ description: long }));
    const text = screen.getByText(/1\. step/);
    expect(text).toHaveClass("line-clamp-12");
    fireEvent.click(screen.getByRole("button", { name: "Show all" }));
    expect(text).not.toHaveClass("line-clamp-12");
  });

  it("links to the files for the SOP", () => {
    const onOpenFiles = vi.fn();
    card(protocol(), onOpenFiles);
    fireEvent.click(screen.getByRole("button", { name: /SOP and files/ }));
    expect(onOpenFiles).toHaveBeenCalled();
  });
});
