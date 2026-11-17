"use client";

import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { type ReactNode, useState } from "react";

/** Opened from ``children``: flags wells as outliers (``flagged`` false) or removes their
 *  flag, with a reason (required on a completed run). An outlier leaves plate QC and the
 *  normalization anchors; nothing changes until the button is pressed. */
export function OutlierFlagPopover({
  flagged,
  title,
  pending,
  reasonRequired = false,
  onSubmit,
  children,
}: {
  flagged: boolean;
  /** What is flagged, e.g. "A1 · Negative control" or "12 wells". */
  title: string;
  pending: boolean;
  /** A completed run's flags change only with a reason. */
  reasonRequired?: boolean;
  /** Called once per press; the popover closes. */
  onSubmit: (reason: string | null) => void;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const action = flagged ? "Remove outlier flag" : "Flag as outlier";
  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) setReason("");
      }}
    >
      <PopoverTrigger asChild>{children}</PopoverTrigger>
      <PopoverContent align="start" className="w-64 p-3">
        <form
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            onSubmit(reason.trim() || null);
            setOpen(false);
            setReason("");
          }}
        >
          <p className="text-sm font-medium">{title}</p>
          <p className="text-xs text-muted-foreground">
            {flagged
              ? "Back into plate QC and the normalization anchors."
              : "Left out of plate QC and the normalization anchors; keeps its own value."}
          </p>
          <Input
            aria-label="Reason"
            placeholder={reasonRequired ? "Reason (required)" : "Reason (optional)"}
            required={reasonRequired}
            maxLength={500}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="h-8 text-sm"
          />
          <Button
            type="submit"
            size="sm"
            className="w-full"
            disabled={pending || (reasonRequired && !reason.trim())}
          >
            {action}
          </Button>
        </form>
      </PopoverContent>
    </Popover>
  );
}
