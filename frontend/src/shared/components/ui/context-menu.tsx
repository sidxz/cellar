"use client";

import { cn } from "@/shared/lib/utils";
import { ChevronRight } from "lucide-react";
import { ContextMenu as Primitive } from "radix-ui";
import type { ComponentProps } from "react";

export const ContextMenu = Primitive.Root;
export const ContextMenuTrigger = Primitive.Trigger;
export const ContextMenuSub = Primitive.Sub;

const contentStyle =
  "z-50 min-w-48 overflow-y-auto rounded-md border bg-popover p-1 text-popover-foreground shadow-md";
const itemStyle =
  "relative flex cursor-default select-none items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none focus:bg-accent focus:text-accent-foreground data-[state=open]:bg-accent data-[disabled]:pointer-events-none data-[disabled]:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0 [&_svg]:text-muted-foreground";

export function ContextMenuContent({
  className,
  ...props
}: ComponentProps<typeof Primitive.Content>) {
  return (
    <Primitive.Portal>
      <Primitive.Content
        className={cn(
          contentStyle,
          "max-h-(--radix-context-menu-content-available-height)",
          className,
        )}
        {...props}
      />
    </Primitive.Portal>
  );
}

export function ContextMenuItem({ className, ...props }: ComponentProps<typeof Primitive.Item>) {
  return <Primitive.Item className={cn(itemStyle, className)} {...props} />;
}

export function ContextMenuLabel({ className, ...props }: ComponentProps<typeof Primitive.Label>) {
  return (
    <Primitive.Label className={cn("px-2 py-1.5 text-sm font-semibold", className)} {...props} />
  );
}

export function ContextMenuSeparator(props: ComponentProps<typeof Primitive.Separator>) {
  return <Primitive.Separator className="-mx-1 my-1 h-px bg-border" {...props} />;
}

export function ContextMenuSubTrigger({
  className,
  children,
  ...props
}: ComponentProps<typeof Primitive.SubTrigger>) {
  return (
    <Primitive.SubTrigger className={cn(itemStyle, className)} {...props}>
      {children}
      <ChevronRight className="ml-auto" />
    </Primitive.SubTrigger>
  );
}

export function ContextMenuSubContent({
  className,
  ...props
}: ComponentProps<typeof Primitive.SubContent>) {
  return (
    <Primitive.Portal>
      <Primitive.SubContent className={cn(contentStyle, className)} {...props} />
    </Primitive.Portal>
  );
}
