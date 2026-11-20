import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ClustersDialog } from "./clusters-dialog";

const open = (compoundCount: number, initialThreshold?: number) => {
  const onApply = vi.fn();
  const onOpenChange = vi.fn();
  render(
    <ClustersDialog
      open
      onOpenChange={onOpenChange}
      compoundCount={compoundCount}
      initialThreshold={initialThreshold}
      onApply={onApply}
    />,
  );
  return { onApply, onOpenChange };
};
const apply = () => screen.getByRole("button", { name: "Add cluster columns" });
const threshold = () => screen.getByLabelText("Cluster threshold (Tanimoto distance)");

describe("ClustersDialog", () => {
  it("clusters at the job's own default threshold, shown and editable", () => {
    const { onApply, onOpenChange } = open(120);
    expect(threshold()).toHaveValue(0.4);
    expect(threshold()).toHaveAttribute("min", "0.05");
    expect(threshold()).toHaveAttribute("max", "0.95");
    expect(threshold()).toHaveAttribute("step", "0.05");
    fireEvent.click(apply());
    expect(onApply).toHaveBeenCalledWith(0.4);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("passes an edited threshold and starts from the current one", () => {
    const { onApply } = open(120, 0.6);
    expect(threshold()).toHaveValue(0.6);
    fireEvent.change(threshold(), { target: { value: "0.25" } });
    fireEvent.click(apply());
    expect(onApply).toHaveBeenCalledWith(0.25);
  });

  it("refuses a threshold outside 0.05–0.95, saying why", () => {
    const { onApply } = open(120);
    fireEvent.change(threshold(), { target: { value: "1.2" } });
    expect(apply()).toBeDisabled();
    expect(screen.getByText("Enter a threshold from 0.05 to 0.95.")).toBeInTheDocument();
    expect(threshold()).toHaveAccessibleDescription(
      expect.stringContaining("Enter a threshold from 0.05 to 0.95."),
    );
    expect(threshold()).toBeInvalid();
    fireEvent.click(apply());
    expect(onApply).not.toHaveBeenCalled();
  });

  it("is disabled below 10 compounds, saying why", () => {
    open(9);
    expect(apply()).toBeDisabled();
    expect(screen.getByText("Clustering needs at least 10 compounds.")).toBeInTheDocument();
    expect(threshold()).toHaveAccessibleDescription(
      expect.stringContaining("Clustering needs at least 10 compounds."),
    );
    expect(threshold()).toBeValid();
  });

  it("is disabled above 50,000 compounds, with the count", () => {
    open(61_204);
    expect(apply()).toBeDisabled();
    expect(threshold()).toHaveAccessibleDescription(expect.stringContaining("61,204"));
  });
});
