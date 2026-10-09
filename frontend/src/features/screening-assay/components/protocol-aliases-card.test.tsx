import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Protocol } from "../types";
import { ProtocolAliasesCard } from "./protocol-aliases-card";

const addMutate = vi.fn();
const removeMutate = vi.fn();

vi.mock("../hooks/use-protocols", () => ({
  useAddProtocolNickname: () => ({ mutate: addMutate, isPending: false }),
  useRemoveProtocolNickname: () => ({ mutate: removeMutate, isPending: false }),
}));

const protocol = {
  id: "p-1",
  name: "M. tuberculosis growth inhibition [resazurin]",
  aliases: [
    { label: "LORA", kind: "nickname", recorded_at: "2026-10-08T00:00:00Z", reason: null },
    {
      label: "Mtb MIC (old)",
      kind: "former",
      recorded_at: "2026-10-08T00:00:00Z",
      reason: "Names generated from fields",
    },
  ],
} as unknown as Protocol;

describe("ProtocolAliasesCard", () => {
  beforeEach(() => {
    addMutate.mockReset();
    removeMutate.mockReset();
  });

  it("adds a trimmed nickname", () => {
    render(<ProtocolAliasesCard protocol={protocol} canEdit />);
    fireEvent.change(screen.getByLabelText("New nickname"), { target: { value: "  MABA " } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(addMutate.mock.calls[0][0]).toBe("MABA");
  });

  it("removes a nickname", () => {
    render(<ProtocolAliasesCard protocol={protocol} canEdit />);
    fireEvent.click(screen.getByRole("button", { name: "Remove LORA" }));
    expect(removeMutate).toHaveBeenCalledWith("LORA");
  });

  it("lists former names", () => {
    render(<ProtocolAliasesCard protocol={protocol} canEdit />);
    expect(screen.getByText("Former names")).toBeInTheDocument();
    expect(screen.getByText(/Mtb MIC \(old\)/)).toBeInTheDocument();
  });

  it("is read-only without edit rights", () => {
    render(<ProtocolAliasesCard protocol={protocol} canEdit={false} />);
    expect(screen.queryByLabelText("New nickname")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove LORA" })).not.toBeInTheDocument();
  });
});
