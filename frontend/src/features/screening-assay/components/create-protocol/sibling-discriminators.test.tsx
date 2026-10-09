import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SiblingDiscriminators, siblingDiscriminatorsPayload } from "./sibling-discriminators";

const sib = (over = {}) => ({
  protocol_id: "p1",
  code: "PRT-00001",
  name: "Microsomal stability",
  discriminator: null,
  status: "draft",
  is_locked: false,
  ...over,
});

describe("SiblingDiscriminators", () => {
  it("offers a field per bare, editable sibling and shows its new name", () => {
    const onChange = vi.fn();
    render(
      <SiblingDiscriminators
        siblings={[sib()]}
        renames={[
          {
            protocol_id: "p1",
            code: "PRT-00001",
            name: "Microsomal stability [mouse]",
            error: null,
          },
        ]}
        values={{ p1: { discriminator: "mouse", reason: "" } }}
        newName="Microsomal stability [human]"
        onChange={onChange}
      />,
    );
    expect(screen.getByText(/PRT-00001 becomes/)).toBeInTheDocument();
    expect(screen.getByText("Microsomal stability [mouse]")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Discriminator for PRT-00001"), {
      target: { value: "rat" },
    });
    expect(onChange).toHaveBeenCalledWith({ p1: { discriminator: "rat", reason: "" } });
  });

  it("asks for a reason on a published sibling and prefills it", () => {
    render(
      <SiblingDiscriminators
        siblings={[sib({ status: "active" })]}
        renames={[]}
        values={{}}
        newName="X [human]"
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByDisplayValue(/Distinguish from the new protocol/)).toBeInTheDocument();
  });

  it("does not offer locked or retired siblings and says they stay flagged", () => {
    render(
      <SiblingDiscriminators
        siblings={[sib({ is_locked: true })]}
        renames={[]}
        values={{}}
        newName="X"
        onChange={vi.fn()}
      />,
    );
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.getByText(/locked/i)).toBeInTheDocument();
  });

  it("names the clash a sibling's new name would cause", () => {
    render(
      <SiblingDiscriminators
        siblings={[sib()]}
        renames={[
          { protocol_id: "p1", code: "PRT-00001", name: null, error: "PRT-00009 has this name" },
        ]}
        values={{ p1: { discriminator: "human", reason: "" } }}
        newName="Microsomal stability [human]"
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText("PRT-00009 has this name")).toBeInTheDocument();
  });
});

describe("siblingDiscriminatorsPayload", () => {
  it("sends filled, offered siblings only, with a reason for published ones", () => {
    const siblings = [
      sib(),
      sib({ protocol_id: "p2", code: "PRT-00002", status: "active" }),
      sib({ protocol_id: "p3", code: "PRT-00003", is_locked: true }),
      sib({ protocol_id: "p4", code: "PRT-00004" }),
    ];
    const values = {
      p1: { discriminator: " mouse ", reason: "" },
      p2: { discriminator: "rat", reason: "" },
      p3: { discriminator: "dog", reason: "" },
      p4: { discriminator: "  ", reason: "" },
      gone: { discriminator: "stale", reason: "" },
    };
    expect(siblingDiscriminatorsPayload(siblings, values, "Microsomal stability [human]")).toEqual([
      { protocol_id: "p1", discriminator: "mouse", reason: null },
      {
        protocol_id: "p2",
        discriminator: "rat",
        reason: "Distinguish from the new protocol (Microsomal stability [human])",
      },
    ]);
  });
});
