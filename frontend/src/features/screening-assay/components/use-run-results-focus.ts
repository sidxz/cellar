"use client";

import { useEffect, useRef, useState } from "react";

/** Maximize a results region without remounting its grid or losing its view. */
export function useRunResultsFocus() {
  const [expanded, setExpanded] = useState(false);
  const resultsRef = useRef<HTMLElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!expanded || !resultsRef.current) return;
    const inertElements: Array<[HTMLElement, boolean]> = [];
    let node: HTMLElement | null = resultsRef.current;
    while (node?.parentElement) {
      for (const sibling of node.parentElement.children) {
        if (sibling !== node && sibling instanceof HTMLElement && sibling.tagName !== "SCRIPT") {
          inertElements.push([sibling, sibling.inert]);
          sibling.inert = true;
        }
      }
      node = node.parentElement;
      if (node === document.body) break;
    }
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    resultsRef.current.focus();
    const onEscape = (event: KeyboardEvent) => {
      if (
        event.key === "Escape" &&
        !event.defaultPrevented &&
        !document.querySelector(
          "[role='dialog'], [data-slot='dropdown-menu-content'], [data-slot='popover-content']",
        )
      ) {
        setExpanded(false);
      }
    };
    document.addEventListener("keydown", onEscape);
    return () => {
      document.body.style.overflow = overflow;
      for (const [element, inert] of inertElements) element.inert = inert;
      document.removeEventListener("keydown", onEscape);
      buttonRef.current?.focus();
    };
  }, [expanded]);

  return { expanded, setExpanded, resultsRef, buttonRef };
}
