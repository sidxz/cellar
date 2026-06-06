import { type RefObject, useEffect } from "react";

/**
 * Calls `onOutside` when a `mousedown` lands outside the referenced element.
 *
 * Extracted from the several hand-rolled copies that each registered a
 * `document.addEventListener("mousedown", ...)` effect to dismiss a dropdown.
 * Pass `enabled: false` to skip the listener entirely (e.g. when the dropdown
 * is closed) — the handler reads the latest `onOutside` on every event, so it
 * never goes stale.
 */
export function useClickOutside(
  ref: RefObject<HTMLElement | null>,
  onOutside: () => void,
  enabled = true,
): void {
  useEffect(() => {
    if (!enabled) return;
    function handleMouseDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onOutside();
      }
    }
    document.addEventListener("mousedown", handleMouseDown);
    return () => document.removeEventListener("mousedown", handleMouseDown);
  }, [ref, onOutside, enabled]);
}
