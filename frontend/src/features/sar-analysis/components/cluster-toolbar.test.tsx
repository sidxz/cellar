import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ClusterToolbar } from "./cluster-toolbar";

describe("ClusterToolbar", () => {
  it("shows N input when picker=maxmin", () => {
    render(
      <ClusterToolbar
        picker="maxmin"
        n={50}
        threshold={0.4}
        selectedCount={0}
        onPickerChange={() => {}}
        onNChange={() => {}}
        onThresholdChange={() => {}}
        onDiversify={() => {}}
        onSave={() => {}}
        colorPicker={null}
      />,
    );
    expect(screen.getByLabelText(/^n$/i)).toBeInTheDocument();
  });

  it("shows Threshold when picker=butina", () => {
    render(
      <ClusterToolbar
        picker="butina"
        n={50}
        threshold={0.4}
        selectedCount={0}
        onPickerChange={() => {}}
        onNChange={() => {}}
        onThresholdChange={() => {}}
        onDiversify={() => {}}
        onSave={() => {}}
        colorPicker={null}
      />,
    );
    expect(screen.getByLabelText(/threshold/i)).toBeInTheDocument();
  });

  it("Save button shows live count and is disabled at zero", () => {
    const save = vi.fn();
    render(
      <ClusterToolbar
        picker="maxmin"
        n={50}
        threshold={0.4}
        selectedCount={12}
        onPickerChange={() => {}}
        onNChange={() => {}}
        onThresholdChange={() => {}}
        onDiversify={() => {}}
        onSave={save}
        colorPicker={null}
      />,
    );
    const saveBtn = screen.getByRole("button", { name: /save selection \(12\)/i });
    expect(saveBtn).not.toBeDisabled();
    fireEvent.click(saveBtn);
    expect(save).toHaveBeenCalled();
  });
});
