"use client";
import { useFontFamilyStore } from "@/shared/lib/stores/font-family-store";
import { type ReactNode, useEffect } from "react";

export function FontFamilyProvider({ children }: { children: ReactNode }) {
  const font = useFontFamilyStore((s) => s.font);
  useEffect(() => {
    document.documentElement.setAttribute("data-font", font);
  }, [font]);
  return <>{children}</>;
}
