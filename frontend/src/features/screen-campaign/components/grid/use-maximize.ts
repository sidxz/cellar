"use client";

import { useEffect, useRef, useState } from "react";

/** The results area filling the window. It expands in place rather than moving into a dialog, so
 *  the grid keeps its sort, scroll and ticks. While maximized the page behind it leaves the
 *  keyboard order and stops scrolling; Esc (outside an open menu or dialog) returns. */
export function useMaximize() {
  const ref = useRef<HTMLElement>(null);
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    if (!maximized) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    // Everything beside the workspace's branch, up to <body>. Menus and dialogs opened later
    // portal to <body> after this runs, so they stay usable.
    const background: { element: HTMLElement; inert: boolean }[] = [];
    let branch = ref.current;
    while (branch && branch !== document.body) {
      for (const sibling of branch.parentElement?.children ?? []) {
        if (sibling instanceof HTMLElement && sibling !== branch) {
          background.push({ element: sibling, inert: sibling.inert });
          sibling.inert = true;
        }
      }
      branch = branch.parentElement;
    }
    const exit = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      if (
        event.target instanceof Element &&
        event.target.closest(
          '[role="dialog"], [role="alertdialog"], [role="menu"], [role="listbox"], [data-radix-popper-content-wrapper]',
        )
      ) {
        return;
      }
      setMaximized(false);
      ref.current?.querySelector<HTMLButtonElement>("[data-maximize]")?.focus();
    };
    document.addEventListener("keydown", exit);
    return () => {
      document.body.style.overflow = previousOverflow;
      for (const { element, inert } of background) element.inert = inert;
      document.removeEventListener("keydown", exit);
    };
  }, [maximized]);

  return { ref, maximized, setMaximized };
}
