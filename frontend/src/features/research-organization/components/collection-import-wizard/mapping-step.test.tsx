import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MappingStep } from "./mapping-step";

describe("MappingStep", () => {
  it("auto-suggests roles from known synonyms", () => {
    render(
      <MappingStep
        headers={["Reg No.", "Compound", "Foo Bar"]}
        rows={[]}
        templates={[]}
        onContinue={vi.fn()}
      />,
    );
    expect(screen.getByDisplayValue("registration_number")).toBeInTheDocument();
    expect(screen.getByDisplayValue("name")).toBeInTheDocument();
    expect(screen.getAllByDisplayValue("ignore").length).toBeGreaterThan(0);
  });

  it("calls onContinue with the user's mapping", () => {
    const onContinue = vi.fn();
    render(
      <MappingStep
        headers={["Reg No."]}
        rows={[]}
        templates={[]}
        onContinue={onContinue}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(onContinue).toHaveBeenCalledWith(
      expect.objectContaining({
        mapping: { registration_number: "Reg No." },
      }),
    );
  });

  it("renders filter chips when templates exist", () => {
    render(
      <MappingStep
        headers={["Reg No."]}
        rows={[]}
        templates={[
          {
            id: "t1",
            name: "shared template",
            column_mapping: { registration_number: "Reg No." },
            used_in_this_collection: false,
            created_by: "other-user",
          },
        ]}
        currentUserId="me"
        selectedTemplateId={null}
        onSelectedTemplateChange={vi.fn()}
        onContinue={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("button", { name: /all \(1\)/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /used here \(0\)/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /mine \(0\)/i }),
    ).toBeInTheDocument();
  });
});
