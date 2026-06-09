import { cn } from "@/shared/lib/utils";
import { BadgeCheck, Boxes, Flame, GitBranch, Library, type LucideIcon, Send } from "lucide-react";
import type { CollectionType } from "../../types";

/** Approved per-type iconography (coverage design §10). `Target`/`Crosshair`
 *  are reserved for the Targets feature; `Share2` reads as "shared" visibility,
 *  so distribution uses `Send`. */
export const COLLECTION_TYPE_ICONS: Record<CollectionType, LucideIcon> = {
  generic: Boxes,
  reference_set: BadgeCheck,
  library: Library,
  hit_list: Flame,
  series: GitBranch,
  distribution_set: Send,
};

export function CollectionTypeIcon({
  type,
  className,
}: {
  type: CollectionType;
  className?: string;
}) {
  const Icon = COLLECTION_TYPE_ICONS[type] ?? Boxes;
  return <Icon className={cn("h-3.5 w-3.5", className)} aria-hidden />;
}
