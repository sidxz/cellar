import { Skeleton } from "@/shared/components/ui/skeleton";
import { cn } from "@/shared/lib/utils";

interface SkeletonListProps {
  /** Number of skeleton rows to render. */
  rows?: number;
  /** Tailwind classes applied to each skeleton row (e.g. height/width). */
  rowClassName?: string;
  /** Classes for the wrapping container (controls inter-row spacing). */
  className?: string;
}

/**
 * Vertical stack of placeholder rows for list/admin loading states.
 *
 * Replaces the hand-inlined `<div className="space-y-3">{Array.from(...)}</div>`
 * block that was copy-pasted across the admin list pages.
 */
export function SkeletonList({
  rows = 3,
  rowClassName = "h-12 w-full",
  className = "space-y-3",
}: SkeletonListProps) {
  return (
    <div className={className}>
      {Array.from({ length: rows }).map((_, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: static placeholder rows, never reordered
        <Skeleton key={i} className={cn(rowClassName)} />
      ))}
    </div>
  );
}
