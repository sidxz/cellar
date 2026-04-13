/**
 * Render a dose-response curve to a canvas and return as base64 PNG.
 * Used for embedding sparkline images in Excel exports.
 */
import { CHART_COLORS, CHART_CANVAS } from "@/shared/lib/chart-colors";

interface CurveImageParams {
  hill_slope: number;
  top: number;
  bottom: number;
  fitted_value: number;
}

interface DataPoint {
  x: number;
  y: number;
}

const WIDTH = 200;
const HEIGHT = 80;
const PAD = 12;

/**
 * Render a 4PL dose-response mini-chart to a base64 PNG string.
 * Returns a data URL-less base64 string suitable for exceljs addImage.
 */
export function renderCurveToBase64(
  params: CurveImageParams,
  dataPoints?: DataPoint[] | null,
  color = CHART_COLORS.primary
): string | null {
  if (typeof document === "undefined") return null; // SSR guard

  const canvas = document.createElement("canvas");
  canvas.width = WIDTH;
  canvas.height = HEIGHT;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  const { hill_slope, top, bottom, fitted_value } = params;
  const plotW = WIDTH - 2 * PAD;
  const plotH = HEIGHT - 2 * PAD;

  // Ranges
  const logMin = Math.log10(Math.max(fitted_value * 0.01, 1e-12));
  const logMax = Math.log10(fitted_value * 100);
  const logRange = logMax - logMin || 1;
  const yMin = Math.min(0, bottom, top);
  const yMax = Math.max(100, bottom, top);
  const yRange = yMax - yMin || 1;

  const toX = (logVal: number) => PAD + ((logVal - logMin) / logRange) * plotW;
  const toY = (yVal: number) => PAD + (1 - (yVal - yMin) / yRange) * plotH;

  // Background (light for Excel)
  ctx.fillStyle = CHART_CANVAS.background;
  ctx.fillRect(0, 0, WIDTH, HEIGHT);

  // Axes
  ctx.strokeStyle = CHART_CANVAS.grid;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(PAD, PAD);
  ctx.lineTo(PAD, PAD + plotH);
  ctx.lineTo(PAD + plotW, PAD + plotH);
  ctx.stroke();

  // 50% gridline
  ctx.strokeStyle = CHART_CANVAS.gridLight;
  ctx.setLineDash([2, 2]);
  ctx.beginPath();
  ctx.moveTo(PAD, toY(50));
  ctx.lineTo(PAD + plotW, toY(50));
  ctx.stroke();
  ctx.setLineDash([]);

  // IC50 vertical dashed line
  const ic50X = toX(Math.log10(fitted_value));
  if (ic50X >= PAD && ic50X <= PAD + plotW) {
    ctx.strokeStyle = color;
    ctx.globalAlpha = 0.5;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(ic50X, PAD);
    ctx.lineTo(ic50X, PAD + plotH);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.globalAlpha = 1;
  }

  // Fitted sigmoid
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.beginPath();
  const N = 50;
  for (let i = 0; i < N; i++) {
    const logX = logMin + (logRange * i) / (N - 1);
    const x = Math.pow(10, logX);
    const y = bottom + (top - bottom) / (1 + Math.pow(x / fitted_value, hill_slope));
    const cx = toX(logX);
    const cy = toY(y);
    if (i === 0) ctx.moveTo(cx, cy);
    else ctx.lineTo(cx, cy);
  }
  ctx.stroke();

  // Data points
  if (dataPoints && dataPoints.length > 0) {
    ctx.fillStyle = color;
    for (const pt of dataPoints) {
      const cx = toX(Math.log10(Math.max(pt.x, 1e-12)));
      const cy = toY(pt.y);
      if (cx >= PAD && cx <= PAD + plotW) {
        ctx.beginPath();
        ctx.arc(cx, cy, 2.5, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }

  // Y-axis labels
  ctx.fillStyle = CHART_CANVAS.label;
  ctx.font = "9px sans-serif";
  ctx.textAlign = "right";
  ctx.fillText("0", PAD - 2, toY(0) + 3);
  ctx.fillText("100", PAD - 2, toY(100) + 3);

  return canvas.toDataURL("image/png").replace("data:image/png;base64,", "");
}
