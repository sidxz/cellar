import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ClusterToolbar } from "./cluster-toolbar";

describe("ClusterToolbar", () => {
  it("shows N input when picker=maxmin", () => {
    render(
      <ClusterToolbar
        picker="maxmin"
        n={50}
        threshold={0.4}
        onPickerChange={() => {}}
        onNChange={() => {}}
        onThresholdChange={() => {}}
        onDiversify={() => {}}
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
        onPickerChange={() => {}}
        onNChange={() => {}}
        onThresholdChange={() => {}}
        onDiversify={() => {}}
        colorPicker={null}
      />,
    );
    expect(screen.getByLabelText(/threshold/i)).toBeInTheDocument();
  });
});
