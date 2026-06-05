import { Badge } from "@/shared/components/ui/badge";
import {
  formatStatusLabel,
  getPriorityVariant,
  getStatusVariant,
} from "@/shared/lib/status-variants";

interface StatusBadgeProps {
  status: string;
  label?: string;
  className?: string;
}

export function StatusBadge({ status, label, className }: StatusBadgeProps) {
  return (
    <Badge variant={getStatusVariant(status)} className={className}>
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
