"use client";
import { useFontFamilyStore } from "@/shared/lib/stores/font-family-store";
import { FONT_SCALE_DEFAULT, useFontScaleStore } from "@/shared/lib/stores/font-scale-store";
import { type ReactNode, useEffect } from "react";

export function FontFamilyProvider({ children }: { children: ReactNode }) {
  const font = useFontFamilyStore((s) => s.font);
  const scale = useFontScaleStore((s) => s.scale);
  useEffect(() => {
    document.documentElement.setAttribute("data-font", font);
  }, [font]);
  useEffect(() => {
    // Empty string removes the inline style at the 100% default so the
    // browser/user-agent baseline stays in charge.
    document.documentElement.style.fontSize = scale === FONT_SCALE_DEFAULT ? "" : `${scale}%`;
  }, [scale]);
  return <>{children}</>;
}
