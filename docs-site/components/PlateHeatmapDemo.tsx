"use client";

import dynamic from "next/dynamic";
import { WidgetPlaceholder } from "./WidgetPlaceholder";

export type {
  PlateFormat,
  PlateHeatmapDemoProps,
  WellValue,
} from "./PlateHeatmapDemo.impl";

/**
 * PlateHeatmapDemo — interactive 96/384-well plate heatmap with per-well
 * hover. Client-only.
 */
export const PlateHeatmapDemo = dynamic(
  () => import("./PlateHeatmapDemo.impl").then((m) => m.PlateHeatmapDemoImpl),
  {
    ssr: false,
    loading: () => <WidgetPlaceholder name="PlateHeatmapDemo" />,
  },
);
