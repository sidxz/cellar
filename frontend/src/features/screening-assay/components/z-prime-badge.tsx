import { Badge } from "@/shared/components/ui/badge";
import { cn } from "@/shared/lib/utils";
import { type ZPrimeQuality, classifyZPrime } from "../lib/qc-metrics";

/**
 * Shared Z' (Z-prime) factor quality presentation.
 *
 * `Z_PRIME_BADGE` maps each quality band to its label + Tailwind color scheme;
 * callers that need bespoke sizing (e.g. the per-plate heatmap header) read the
 * map directly, while `ZPrimeBadge` is the standard rendering. Keep both here so
 * the Z' color scheme lives in exactly one place.
 */
export const Z_PRIME_BADGE: Record<ZPrimeQuality, { label: string; className: string }> = {
  excellent: {
    label: "Excellent",
    className: "bg-green-500/20 text-green-400 border-green-500/30",
  },
  marginal: {
    label: "Marginal",
    className: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  },
  poor: {
    label: "Poor",
    className: "bg-destructive/20 text-destructive border-destructive/30",
  },
};

/** Z' factor quality badge. */
export function ZPrimeBadge({ value }: { value: number }) {
  const { label, className } = Z_PRIME_BADGE[classifyZPrime(value)];
  return (
    <Badge variant="outline" className={cn("text-xs font-medium", className)}>
      {label}
    </Badge>
  );
}
