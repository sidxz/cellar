import { Button } from "@/shared/components/ui/button";
import type { LucideIcon } from "lucide-react";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: {
    label: string;
    onClick: () => void;
    icon?: LucideIcon;
  };
}

export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
      <Icon className="h-12 w-12 text-muted-foreground/40" />
      <h3 className="mt-4 text-lg font-semibold">{title}</h3>
      <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      {action && (
        <Button className="mt-4" size="sm" onClick={action.onClick}>
          {action.icon && <action.icon className="mr-2 h-4 w-4" />}
          {action.label}
        </Button>
      )}
    </div>
  );
}

interface ErrorStateProps {
  message: string;
  details?: string;
}

export function ErrorState({ message, details }: ErrorStateProps) {
  return (
    <div className="rounded-lg border border-dashed border-destructive/50 p-8 text-center">
      <p className="text-sm text-destructive">{message}</p>
      {details && <p className="mt-1 text-xs text-muted-foreground">{details}</p>}
    </div>
  );
}
