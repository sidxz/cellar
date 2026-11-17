import { themeQuartz } from "ag-grid-community";

/**
 * AG Grid theme that inherits from the app's CSS custom properties.
 * Follows the global theme, font family, and root text-size preference.
 */
export const cellarTheme = themeQuartz.withParams({
  backgroundColor: "var(--background)",
  foregroundColor: "var(--foreground)",
  borderColor: "var(--border)",
  headerBackgroundColor: "var(--muted)",
  headerFontWeight: 500,
  headerTextColor: "var(--foreground)",
  rowHoverColor: "color-mix(in oklch, var(--muted) 50%, transparent)",
  selectedRowBackgroundColor: "var(--accent)",
  oddRowBackgroundColor: "transparent",
  cellTextColor: "var(--foreground)",
  fontFamily: "var(--font-sans)",
  fontSize: "var(--text-sm, 0.875rem)",
  headerFontSize: "var(--text-sm, 0.875rem)",
  rowBorder: { color: "var(--border)", style: "solid", width: 1 },
  columnBorder: false,
  wrapperBorderRadius: "var(--radius-lg)",
  wrapperBorder: { color: "var(--border)", style: "solid", width: 1 },
  spacing: 4,
});
