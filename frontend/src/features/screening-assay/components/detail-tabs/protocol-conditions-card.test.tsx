import { fireEvent, render, screen } from "@testing-library/react";
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

const card = (conditions: ConditionDefinition[], onOpenDesign = vi.fn()) =>
  render(
    <ProtocolConditionsCard
      protocol={{ condition_definitions: conditions } as unknown as Protocol}
      onOpenDesign={onOpenDesign}
    />,
  );

describe("ProtocolConditionsCard", () => {
  it("lists every condition: a fixed value with its unit, or what each run enters", () => {
    card([
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
      cond({ name: "Incubation time", data_type: "numeric", unit: "h" }),
      cond({
        name: "Atmosphere",
        data_type: "pick_list",
        pick_list_values: ["aerobic", "hypoxic"],
      }),
      cond({ name: "Medium" }),
    ]);
    expect(screen.getByText("Hypoxia").nextSibling).toHaveTextContent("yes");
    expect(screen.getByText("Substrate concentration").nextSibling).toHaveTextContent("25 µM");
    expect(screen.getByText("Incubation time").nextSibling).toHaveTextContent("varies per run (h)");
    expect(screen.getByText("Atmosphere").nextSibling).toHaveTextContent(
      "varies per run (one of aerobic, hypoxic)",
    );
    expect(screen.getByText("Medium").nextSibling).toHaveTextContent(/^varies per run$/);
  });

  it("says when none are recorded", () => {
    card([]);
    expect(screen.getByText(/No conditions recorded/)).toBeInTheDocument();
  });

  it("opens the Design tab, where conditions are edited", () => {
    const onOpenDesign = vi.fn();
    card([], onOpenDesign);
    fireEvent.click(screen.getByRole("button", { name: /Open in Design/ }));
    expect(onOpenDesign).toHaveBeenCalled();
  });
});
