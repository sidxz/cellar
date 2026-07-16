"use client";

import { RotateCcw } from "lucide-react";

import { Slider } from "@/shared/components/ui/slider";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/shared/components/ui/tooltip";
import {
  FONT_SCALE_DEFAULT,
  FONT_SCALE_MAX,
  FONT_SCALE_MIN,
  FONT_SCALE_STEP,
  useFontScaleStore,
} from "@/shared/lib/stores/font-scale-store";

/** Global text-size slider — sets the root font-size (percent of browser
 *  default); every rem-based utility scales off it. Sits next to the theme
 *  toggle in the top bar. */
export function FontSizeControl() {
  const scale = useFontScaleStore((s) => s.scale);
  const setScale = useFontScaleStore((s) => s.setScale);
  const reset = useFontScaleStore((s) => s.reset);
  const isDefault = scale === FONT_SCALE_DEFAULT;

  return (
    <TooltipProvider delayDuration={300}>
      <div className="hidden items-center gap-1.5 px-1 lg:flex">
        <span aria-hidden className="text-xs font-semibold text-muted-foreground">
          A
        </span>
        <Tooltip>
          <TooltipTrigger asChild>
            <div className="flex items-center">
              <Slider
                value={[scale]}
                min={FONT_SCALE_MIN}
                max={FONT_SCALE_MAX}
                step={FONT_SCALE_STEP}
                onValueChange={([v]) => setScale(v)}
                onDoubleClick={reset}
                aria-label="Text size"
                className="w-16"
              />
            </div>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            Text size {scale}%{isDefault ? "" : " · double-click to reset"}
          </TooltipContent>
        </Tooltip>
        <span aria-hidden className="text-base font-semibold text-muted-foreground">
          A
        </span>
        {!isDefault && (
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={reset}
                aria-label="Reset text size to 100%"
                className="rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground"
              >
                <RotateCcw className="size-3.5" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom">Reset to 100%</TooltipContent>
          </Tooltip>
        )}
      </div>
    </TooltipProvider>
  );
}
