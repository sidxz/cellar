import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProtocolNamePreview, isPreviewSavable } from "./protocol-name-preview";

const base = {
  name: "M. tuberculosis growth inhibition [resazurin]",
  base: "M. tuberculosis growth inhibition",
  missing: [],
  missing_labels: [],
  clash: null,
  siblings: [],
  needs_discriminator: false,
  discriminator_error: null,
  discriminator_in_pattern: false,
  sibling_renames: [],
};

describe("ProtocolNamePreview", () => {
  it("shows the name and that the code comes on save", () => {
    render(<ProtocolNamePreview preview={base} isFetching={false} />);
    expect(screen.getByText("M. tuberculosis growth inhibition [resazurin]")).toBeInTheDocument();
    expect(screen.getByText(/code is assigned when you create/i)).toBeInTheDocument();
    expect(isPreviewSavable(base)).toBe(true);
  });

  it("lists what is missing", () => {
    const p = { ...base, missing: ["organism"], missing_labels: ["an organism"] };
    render(<ProtocolNamePreview preview={p} isFetching={false} />);
    expect(screen.getByText(/needs an organism/i)).toBeInTheDocument();
    expect(isPreviewSavable(p)).toBe(false);
  });

  it("explains a clash with the other code", () => {
    const p = {
      ...base,
      clash: {
        protocol_id: "x",
        code: "PRT-00002",
        name: base.name,
        discriminator: "resazurin",
        status: "draft",
        is_locked: false,
      },
    };
    render(<ProtocolNamePreview preview={p} isFetching={false} />);
    expect(screen.getByText(/PRT-00002/)).toBeInTheDocument();
    expect(isPreviewSavable(p)).toBe(false);
  });

  it("asks for a discriminator when siblings share the name", () => {
    const sib = {
      protocol_id: "y",
      code: "PRT-00003",
      name: "M. tuberculosis growth inhibition [OD600]",
      discriminator: "OD600",
      status: "draft",
      is_locked: false,
    };
    const p = { ...base, name: base.base, siblings: [sib], needs_discriminator: true };
    render(<ProtocolNamePreview preview={p} isFetching={false} />);
    expect(screen.getByText(/add a discriminator/i)).toBeInTheDocument();
  });

  it("shows an existing protocol's code instead of the create hint", () => {
    render(<ProtocolNamePreview preview={base} isFetching={false} code="PRT-00012" />);
    expect(screen.getByText(/PRT-00012/)).toBeInTheDocument();
    expect(screen.queryByText(/assigned when you create/i)).not.toBeInTheDocument();
  });

  it("names each sibling by its full name", () => {
    const sib = {
      protocol_id: "y",
      code: "PRT-00019",
      name: "Microsomal stability [human]",
      discriminator: "human",
      status: "draft",
      is_locked: false,
    };
    const p = {
      ...base,
      name: "Microsomal stability",
      base: "Microsomal stability",
      siblings: [sib],
      needs_discriminator: true,
    };
    render(<ProtocolNamePreview preview={p} isFetching={false} />);
    expect(screen.getByText(/PRT-00019 Microsomal stability \[human\]/)).toBeInTheDocument();
  });

  it("is not savable while a sibling's new name would clash", () => {
    const p = {
      ...base,
      sibling_renames: [{ protocol_id: "y", code: "PRT-00019", name: null, error: "clash" }],
    };
    expect(isPreviewSavable(p)).toBe(false);
  });
});
