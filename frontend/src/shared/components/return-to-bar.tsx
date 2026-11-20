"use client";

import { ArrowLeft } from "lucide-react";
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
    ? `Back to ${target.label} with ${protocolCode || "this protocol"}`
    : `Back to ${target.label}`;
  return (
    // Hard to miss on purpose: the way back is the reason the scientist came here.
    <div className="flex flex-wrap items-center gap-3 rounded-md bg-foreground px-3 py-2 text-sm text-background shadow-sm">
      <span className="font-medium">Opened from {target.label}</span>
      <Button
        asChild
        size="sm"
        className="bg-lime-400 font-semibold text-black shadow-[0_0_12px_rgba(163,230,53,0.6)] hover:bg-lime-300"
      >
        <a href={returnHref(target, protocolId)}>
          <ArrowLeft className="size-4" /> {label}
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
