"use client";

import { Button } from "@/shared/components/ui/button";
import { Hexagon } from "lucide-react";
import { useCallback, useState } from "react";

/** Whether a grid draws structures (taller rows), kept per browser under `key`. */
export function useStructuresChoice(key: string): [boolean, (show: boolean) => void] {
  const [show, setShow] = useState(() => {
    try {
      return localStorage.getItem(key) === "1";
    } catch {
      return false;
    }
  });
  const save = useCallback(
    (next: boolean) => {
      setShow(next);
      try {
        localStorage.setItem(key, next ? "1" : "0");
      } catch {
        // Storage unavailable: the choice holds for this visit only.
      }
    },
    [key],
  );
  return [show, save];
}

/** The Structures switch of a results grid's toolbar. */
export function StructuresToggle({
  pressed,
  onPressedChange,
  disabled,
  className,
}: {
  pressed: boolean;
  onPressedChange: (pressed: boolean) => void;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <Button
      type="button"
      variant={pressed ? "secondary" : "outline"}
      size="sm"
      aria-pressed={pressed}
      disabled={disabled}
      onClick={() => onPressedChange(!pressed)}
      className={className}
      title={pressed ? "Hide compound structures" : "Show compound structures"}
    >
      <Hexagon className="mr-1.5 h-4 w-4" />
      Structures
    </Button>
  );
}
