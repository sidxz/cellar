import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { WorkbenchProvider } from "../store/workbench-context";
import { WorkbenchBody } from "./workbench-body";

const show = (editor?: ReactNode) =>
  render(
    <WorkbenchProvider initialPanels={[]}>
      <WorkbenchBody
        plots={<p>plots</p>}
        table={<p>table</p>}
        rail={<input aria-label="Rail field" />}
        editor={editor}
      />
    </WorkbenchProvider>,
  );

describe("WorkbenchBody", () => {
  it("moves focus into the filters overlay, and Escape returns it to the tab", () => {
    show();
    const tab = screen.getByRole("button", { name: "Filters (0)" });
    tab.focus();
    fireEvent.click(tab);
    expect(tab).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "Close filters" })).toHaveFocus();
    fireEvent.keyDown(screen.getByRole("textbox", { name: "Rail field" }), { key: "Escape" });
    expect(tab).toHaveAttribute("aria-expanded", "false");
    expect(tab).toHaveFocus();
  });

  it("returns focus to the tab when the overlay's close button is used", () => {
    show();
    const tab = screen.getByRole("button", { name: "Filters (0)" });
    fireEvent.click(tab);
    fireEvent.click(screen.getByRole("button", { name: "Close filters" }));
    expect(tab).toHaveFocus();
  });
});
