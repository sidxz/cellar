import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ConditionDefinition, Protocol } from "../../types";
import { ProtocolConditionsCard } from "./protocol-conditions-card";

const cond = (over: Partial<ConditionDefinition>): ConditionDefinition => ({
  id: over.name ?? "c",
  name: "c",
  data_type: "text",
  unit: null,
  pick_list_values: null,
  fixed_value: null,
  ...over,
});

const card = (
  conditions: ConditionDefinition[],
  actions = { onAdd: vi.fn(), onEdit: vi.fn(), onRemove: vi.fn() },
) =>
  render(
    <ProtocolConditionsCard
      protocol={{ condition_definitions: conditions } as unknown as Protocol}
      canAdd
      canEdit
      {...actions}
    />,
  );

describe("ProtocolConditionsCard", () => {
  it("lists what each run records, and marks the rare fixed value", () => {
    card([
      cond({ name: "Incubation time", data_type: "numeric", unit: "h" }),
      cond({
        name: "Atmosphere",
        data_type: "pick_list",
        pick_list_values: ["aerobic", "hypoxic"],
      }),
      cond({ name: "Medium" }),
      cond({
        name: "Hypoxia",
        data_type: "pick_list",
        pick_list_values: ["yes", "no"],
        fixed_value: "yes",
      }),
      cond({
        name: "Substrate concentration",
        data_type: "numeric",
        unit: "µM",
        fixed_value: "25",
      }),
    ]);
    const row = (name: string) => within(screen.getByText(name).closest("tr") as HTMLElement);
    expect(row("Incubation time").getByText("h")).toBeInTheDocument();
    expect(row("Atmosphere").getByText("aerobic, hypoxic")).toBeInTheDocument();
    expect(row("Medium").getByText("Varies per run")).toBeInTheDocument();
    expect(row("Hypoxia").getByText("yes")).toBeInTheDocument();
    expect(row("Substrate concentration").getByText("25 µM")).toBeInTheDocument();
  });

  it("says when none are recorded", () => {
    card([]);
    expect(screen.getByText(/None yet. Add what each run records/)).toBeInTheDocument();
  });

  it("provides add, edit and delete directly in Assay conditions", () => {
    const actions = { onAdd: vi.fn(), onEdit: vi.fn(), onRemove: vi.fn() };
    card([cond({ id: "c1", name: "Medium" })], actions);
    fireEvent.click(screen.getByRole("button", { name: "Add condition" }));
    expect(actions.onAdd).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "Edit Medium" }));
    expect(actions.onEdit).toHaveBeenCalledWith("c1");
    fireEvent.click(screen.getByRole("button", { name: "Delete Medium" }));
    expect(actions.onRemove).toHaveBeenCalledWith("c1");
  });
});
