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

  it("blocks Continue and warns when the template name duplicates an existing one", () => {
    const onContinue = vi.fn();
    render(
      <MappingStep
        headers={["Reg No."]}
        rows={[]}
        templates={[
          {
            id: "t1",
            name: "My Map",
            column_mapping: { registration_number: "Reg No." },
            used_in_this_collection: false,
            created_by: "me",
          },
        ]}
        currentUserId="me"
        onContinue={onContinue}
      />,
    );
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.change(screen.getByPlaceholderText(/template name/i), {
      target: { value: "My Map" },
    });
    expect(screen.getByText(/already exists/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /continue/i })).toBeDisabled();
  });

  it("blocks Continue when save is checked but no name is given", () => {
    render(
      <MappingStep
        headers={["Reg No."]}
        rows={[]}
        templates={[]}
        onContinue={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("checkbox"));
    expect(screen.getByRole("button", { name: /continue/i })).toBeDisabled();
  });

  it("surfaces a template save error from the wizard", () => {
    render(
      <MappingStep
        headers={["Reg No."]}
        rows={[]}
        templates={[]}
        onContinue={vi.fn()}
        templateError="Couldn't save template &quot;X&quot;"
      />,
    );
    expect(screen.getByText(/couldn't save template/i)).toBeInTheDocument();
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
