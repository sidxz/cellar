import { Badge } from "@/shared/components/ui/badge";
import {
  type BadgeVariant,
  formatStatusLabel,
  getPriorityVariant,
  getStatusVariant,
} from "@/shared/lib/status-variants";

interface StatusBadgeProps {
  status: string;
  label?: string;
  /** Override the global status→variant mapping (e.g. a domain whose status
   * word collides with a differently-coloured one another domain owns). */
  variant?: BadgeVariant;
  className?: string;
}

export function StatusBadge({ status, label, variant, className }: StatusBadgeProps) {
  return (
    <Badge variant={variant ?? getStatusVariant(status)} className={className}>
      {label ?? formatStatusLabel(status)}
    </Badge>
  );
}

interface PriorityBadgeProps {
  priority: string;
  label?: string;
  className?: string;
}

export function PriorityBadge({ priority, label, className }: PriorityBadgeProps) {
  return (
    <Badge variant={getPriorityVariant(priority)} className={className}>
      {label ?? formatStatusLabel(priority)}
    </Badge>
  );
}
