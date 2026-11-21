"use client";

import { ArrowRight, Link2 } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { Button } from "@/shared/components/ui/button";
import { useAppConfig } from "@/shared/lib/app-config";
import { type ReturnTarget, returnHref, trustedReturnTarget } from "@/shared/lib/return-to";

/** The trusted app this page was opened from (`?return_to=`), or null. */
export function useReturnTarget(): ReturnTarget | null {
  const searchParams = useSearchParams();
  const { returnOrigins } = useAppConfig();
  return trustedReturnTarget(searchParams.get("return_to"), returnOrigins);
}

interface ReturnToBarProps {
  target: ReturnTarget;
  /** Go back with this protocol. */
  protocolId?: string;
  protocolCode?: string | null;
}

export function ReturnToBar({ target, protocolId, protocolCode }: ReturnToBarProps) {
  const label = protocolId
    ? `Continue in ${target.label} with ${protocolCode || "this protocol"}`
    : `Continue in ${target.label}`;
  return (
    // Hard to miss on purpose: the way back is the reason the scientist came here.
    // Message left, action right, like any app banner; wraps under the message when narrow.
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-lg bg-foreground px-4 py-2.5 text-sm text-background shadow-sm">
      <div className="flex min-w-0 items-center gap-2.5">
        <Link2 className="size-4 shrink-0 opacity-70" aria-hidden />
        <span className="font-medium">Opened from {target.label}</span>
      </div>
      <Button
        asChild
        size="sm"
        className="shrink-0 bg-lime-400 font-semibold text-black shadow-[0_0_12px_rgba(163,230,53,0.6)] hover:bg-lime-300"
      >
        <a href={returnHref(target, protocolId)}>
          {label} <ArrowRight className="size-4" />
        </a>
      </Button>
    </div>
  );
}

function BarFromUrl(props: Omit<ReturnToBarProps, "target">) {
  const target = useReturnTarget();
  return target ? <ReturnToBar target={target} {...props} /> : null;
}

/** The bar for a page that does not otherwise read the URL (reading it needs a Suspense boundary). */
export function ReturnToBarFromUrl(props: Omit<ReturnToBarProps, "target">) {
  return (
    <Suspense fallback={null}>
      <BarFromUrl {...props} />
    </Suspense>
  );
}
