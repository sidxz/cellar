import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Command, CommandGroup, CommandInput, CommandItem, CommandList } from "./command";

const realScrollIntoView = Element.prototype.scrollIntoView;
afterEach(() => {
  Element.prototype.scrollIntoView = realScrollIntoView;
});

describe("CommandList", () => {
  it("returns to the top match when the search changes", () => {
    Element.prototype.scrollIntoView = () => {};
    render(
      <Command>
        <CommandInput placeholder="Search" />
        <CommandList>
          <CommandGroup>
            <CommandItem>Ppx1 tuberculosis</CommandItem>
            <CommandItem>PptT tuberculosis</CommandItem>
          </CommandGroup>
        </CommandList>
      </Command>,
    );
    const list = document.querySelector("[data-slot='command-list']") as HTMLElement;
    // What the browser does when cmdk scrolls a row that is no longer the top match into view.
    Element.prototype.scrollIntoView = () => {
      list.scrollTop = 61;
    };

    // "ppt" moves PptT above the previously highlighted Ppx1.
    fireEvent.change(screen.getByPlaceholderText("Search"), { target: { value: "ppt" } });

    expect(list.scrollTop).toBe(0);
  });
});
