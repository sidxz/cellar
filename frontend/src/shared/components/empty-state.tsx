import { Button } from "@/shared/components/ui/button";
import type { LucideIcon } from "lucide-react";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
    icon?: LucideIcon;
  };
  /**
   * `default` renders the full bordered-dashed card (icon + heading + description).
   * `inline` renders a compact, borderless icon + one-line message for tight
   * list/admin panels where the full card would be too heavy.
   */
  variant?: "default" | "inline";
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  variant = "default",
}: EmptyStateProps) {
  if (variant === "inline") {
    return (
      <div className="mt-12 flex flex-col items-center gap-2 text-muted-foreground">
        <Icon className="h-10 w-10" />
        <p>{title}</p>
        {description && <p className="text-sm">{description}</p>}
        {action && (
          <Button className="mt-2" size="sm" onClick={action.onClick}>
            {action.icon && <action.icon className="mr-2 h-4 w-4" />}
            {action.label}
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
      <Icon className="h-12 w-12 text-muted-foreground/40" />
      <h3 className="mt-4 text-lg font-semibold">{title}</h3>
      {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
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
