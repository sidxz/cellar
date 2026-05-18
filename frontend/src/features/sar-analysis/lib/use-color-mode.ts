"use client";

import { useCallback, useState } from "react";
import { useSearchParams } from "next/navigation";
import type { ColorMode } from "@/features/sar-analysis/types";

/**
 * URL state for the UMAP cluster-map color mode.
 *
 * Supported modes:
 * - "cluster"   Color points by cluster assignment (default for UMAP view).
 * - "activity"  Color by activity value for a chosen protocol.
 * - "scaffold"  Color by Bemis-Murcko scaffold chemotype.
 * - "none"      Uniform color — no semantic mapping.
 *
 * When mode is "activity", an optional protocolId is persisted as
 * `?color-protocol=<uuid>` so the selection survives refresh.
 *
 * Local React state is the source of truth (mirrors use-tree-sub-mode pattern).
 * URL is a side-effect via window.history.replaceState so deep-linked URLs
 * land in the correct mode on mount.
 *
 * URL shape:
 *   ?color=activity&color-protocol=<uuid>
 *   ?color=scaffold
 *   (absent) → defaultMode
 */

const COLOR_PARAM = "color";
const PROTOCOL_PARAM = "color-protocol";

interface ColorModeState {
  mode: ColorMode;
  protocolId: string | null;
  setMode: (next: ColorMode, protocol?: string) => void;
}

function writeUrl(
  next: ColorMode,
  defaultMode: ColorMode,
  protocol?: string,
): void {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  if (next === defaultMode) {
    url.searchParams.delete(COLOR_PARAM);
  } else {
    url.searchParams.set(COLOR_PARAM, next);
  }
  if (next === "activity" && protocol) {
    url.searchParams.set(PROTOCOL_PARAM, protocol);
  } else {
    url.searchParams.delete(PROTOCOL_PARAM);
  }
  window.history.replaceState({}, "", url.toString());
}

export function useColorMode(opts: {
  defaultMode: ColorMode;
}): ColorModeState {
  const params = useSearchParams();

  // Read URL once on mount; subsequent state is React-owned.
  const [mode, setMode_] = useState<ColorMode>(() => {
    const raw = params.get(COLOR_PARAM) as ColorMode | null;
    if (raw && ["cluster", "activity", "scaffold", "none"].includes(raw)) {
      return raw;
    }
    return opts.defaultMode;
  });

  const [protocolId, setProtocolId_] = useState<string | null>(() =>
    params.get(PROTOCOL_PARAM),
  );

  const setMode = useCallback(
    (next: ColorMode, protocol?: string) => {
      setMode_(next);
      if (next === "activity" && protocol) {
        setProtocolId_(protocol);
      } else {
        setProtocolId_(null);
      }
      writeUrl(next, opts.defaultMode, protocol);
    },
    [opts.defaultMode],
  );

  return { mode, protocolId, setMode };
}
