import { resolveCategoryColor } from "@/shared/lib/category-colors";
import { cn } from "@/shared/lib/utils";
import { X } from "lucide-react";

interface TagChipProps {
  tagKey: string;
  value: string | null;
  /** When provided, renders a remove (×) button. */
  onRemove?: () => void;
  /** When provided, the chip is a button (e.g. click-to-filter). */
  onClick?: () => void;
  className?: string;
  title?: string;
}

export function TagChip({ tagKey, value, onRemove, onClick, className, title }: TagChipProps) {
  const color = resolveCategoryColor(tagKey);
  const label = value ? `${tagKey}=${value}` : tagKey;
  const Wrapper = onClick ? "button" : "span";
  return (
    <Wrapper
      type={onClick ? "button" : undefined}
      onClick={onClick}
      title={title ?? label}
      className={cn(
        "inline-flex w-fit shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium",
        color.bg,
        onClick && "cursor-pointer transition-colors hover:brightness-110",
        className,
      )}
    >
      <span className={cn("font-semibold", color.text)}>{tagKey}</span>
      {value && (
        <>
          <span className="text-muted-foreground/70">=</span>
          <span className="text-foreground/90">{value}</span>
        </>
      )}
      {onRemove && (
        <button
          type="button"
          aria-label={`Remove ${label}`}
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          className="-mr-0.5 ml-0.5 rounded-full text-muted-foreground/60 hover:text-destructive"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </Wrapper>
  );
}
