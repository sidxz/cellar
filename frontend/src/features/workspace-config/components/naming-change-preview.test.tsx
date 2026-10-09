import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { NamingChangePreview } from "./naming-change-preview";

const changes = [
  {
    protocol_id: "a",
    code: "PRT-00001",
    before: "M. tuberculosis growth inhibition [resazurin]",
    after: "Mtb growth inhibition [resazurin]",
  },
  {
    protocol_id: "b",
    code: "PRT-00002",
    before: "M. tuberculosis growth inhibition [OD600]",
    after: "Mtb growth inhibition [OD600]",
  },
];

describe("NamingChangePreview", () => {
  it("lists before and after and applies on request", () => {
    const onApply = vi.fn();
    render(
      <NamingChangePreview
        open
        onOpenChange={() => {}}
        preview={{ changes, collisions: [] }}
        isLoading={false}
        onApply={onApply}
        isApplying={false}
      />,
    );
    expect(screen.getByText("Mtb growth inhibition [resazurin]")).toBeInTheDocument();
    expect(screen.getByText(/2 protocols will be renamed/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(onApply).toHaveBeenCalled();
  });

  it("blocks Apply while two protocols would share a name", () => {
    render(
      <NamingChangePreview
        open
        onOpenChange={() => {}}
        preview={{
          changes,
          collisions: [{ name: "Mtb growth inhibition", codes: ["PRT-00001", "PRT-00003"] }],
        }}
        isLoading={false}
        onApply={() => {}}
        isApplying={false}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("PRT-00001, PRT-00003");
    expect(screen.getByRole("button", { name: "Apply" })).toBeDisabled();
  });
});
