"use client";

import { cn } from "@/shared/lib/utils";

/**
 * Numbered step-progress strip shared by the import/registration wizards.
 *
 * Renders one bordered circle per step (the step number), a label beside it,
 * and a connector bar between steps. The active step is primary-tinted;
 * completed steps go green; upcoming steps are muted. This replaces the four
 * near-identical local `StepIndicator` definitions that had already drifted
 * (e.g. "Mapping" vs "Map" labels).
 *
 * `current` is 1-indexed (step 1 is the first). Callers that track a 0-indexed
 * step pass `current + 1`.
 */
interface WizardStepIndicatorProps {
  /** Ordered step labels, e.g. ["Upload", "Mapping", "Preview", "Confirm"]. */
  steps: string[];
  /** The active step, 1-indexed. Steps before it render as completed. */
  current: number;
  /** Optional wrapper className (e.g. extra bottom margin). */
  className?: string;
}

export function WizardStepIndicator({ steps, current, className }: WizardStepIndicatorProps) {
  if (steps.length === 0) return null;

  return (
    <nav className={cn("flex items-center gap-2 text-xs", className)} aria-label="Wizard steps">
      {steps.map((label, i) => {
        const n = i + 1;
        const active = current === n;
        const done = current > n;
        return (
          <div key={label} className="flex items-center gap-2">
            <span
              className={cn(
                "flex h-6 w-6 items-center justify-center rounded-full border text-[10px] font-medium",
                active && "border-primary bg-primary/10 text-primary",
                done && "border-green-500 bg-green-500/10 text-green-400",
                !active && !done && "border-muted text-muted-foreground",
              )}
            >
              {n}
            </span>
            <span className={cn(active ? "text-foreground" : "text-muted-foreground")}>
              {label}
            </span>
            {i < steps.length - 1 && <span className="mx-1 h-px w-6 bg-border" />}
          </div>
        );
      })}
    </nav>
  );
}
