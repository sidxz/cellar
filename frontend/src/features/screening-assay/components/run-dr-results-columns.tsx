import type { ColDef, ICellRendererParams } from "ag-grid-community";
import type { RefObject } from "react";
import type { CurveFrame } from "../lib/curve-frame";
import {
  type InterceptDisplay,
  doseRange,
  findInterceptValue,
  formatInterceptDisplay,
  interceptLabel,
} from "../lib/intercept-label";
import type { InterceptSpec } from "../types";
import {
  RunCompoundCell,
  RunResponseCell,
  RunResultsMaximizeHeader,
  RunStructureCell,
} from "./run-dr-results-cells";
import type { CompoundCurveRow } from "./run-dr-results-transforms";
import { displayDoseUnit, doseUnitScale } from "./run-dr-results-view";

export const RUN_DIAGNOSTIC_COLUMNS = ["r_squared", "hill_slope", "num_points"];

interface ColumnOptions {
  query?: string;
  compact?: boolean;
  diagnostics?: boolean;
  /** Set only when every row shares a known unit. Mixed units remain explicit in each cell. */
  unit?: string | null;
  onView?: (moleculeId: string) => void;
  expanded?: boolean;
  onToggleFocus?: () => void;
  focusButtonRef?: RefObject<HTMLButtonElement | null>;
}

export function buildColumnDefs(
  intercepts: InterceptSpec[],
  frame?: CurveFrame,
  options: ColumnOptions = {},
): ColDef<CompoundCurveRow>[] {
  return [
    {
      headerName: "Compound & aliases",
      field: "registration_number",
      initialPinned: "left",
      initialWidth: 260,
      minWidth: 224,
      maxWidth: 360,
      autoHeight: true,
      wrapText: true,
      cellStyle: { lineHeight: "1.3", display: "flex", alignItems: "center" },
      getQuickFilterText: ({ data }) =>
        data
          ? [
              data.registration_number,
              data.molecule_name,
              data.batch_number,
              ...(data.synonyms ?? []),
            ]
              .filter(Boolean)
              .join(" ")
          : "",
      cellRenderer: ({ data }: ICellRendererParams<CompoundCurveRow>) =>
        data ? <RunCompoundCell data={data} query={options.query} /> : null,
    },
    {
      headerName: "Structure",
      colId: "structure",
      initialWidth: 216,
      minWidth: 208,
      maxWidth: 280,
      sortable: false,
      filter: false,
      cellStyle: { padding: 0 },
      cellRenderer: ({ data }: ICellRendererParams<CompoundCurveRow>) =>
        data ? <RunStructureCell data={data} /> : null,
    },
    ...buildInterceptColumns(intercepts, options),
    {
      headerName: "Response & class",
      headerTooltip:
        "Curves share the same axes. Concentration uses a logarithmic scale in the run's original units.",
      colId: "sparkline",
      field: "curve_class",
      initialWidth: 360,
      initialFlex: 1,
      minWidth: 340,
      maxWidth: 420,
      cellRenderer: ({ data }: ICellRendererParams<CompoundCurveRow>) =>
        data ? (
          <RunResponseCell
            data={data}
            frame={frame}
            compact={options.compact}
            onView={options.onView}
          />
        ) : null,
    },
    {
      headerName: "R²",
      field: "r_squared",
      initialWidth: 100,
      minWidth: 90,
      initialHide: !options.diagnostics,
      valueFormatter: (p) => (p.value != null ? Number(p.value).toFixed(3) : "—"),
      type: "numericColumn",
      filter: false,
      cellClass: "tabular-nums",
      cellStyle: { display: "flex", alignItems: "center", justifyContent: "flex-end" },
    },
    {
      headerName: "Hill slope",
      field: "hill_slope",
      initialWidth: 120,
      minWidth: 112,
      initialHide: !options.diagnostics,
      valueFormatter: (p) => (p.value != null ? Number(p.value).toFixed(2) : "—"),
      type: "numericColumn",
      filter: false,
      cellClass: "tabular-nums",
      cellStyle: { display: "flex", alignItems: "center", justifyContent: "flex-end" },
    },
    {
      headerName: "Points",
      field: "num_points",
      initialWidth: 100,
      minWidth: 96,
      initialHide: !options.diagnostics,
      type: "numericColumn",
      filter: false,
      cellStyle: { display: "flex", alignItems: "center", justifyContent: "flex-end" },
    },
    ...(options.onToggleFocus
      ? [
          {
            colId: "__table_controls__",
            headerName: "",
            pinned: "right",
            lockPinned: true,
            lockPosition: "right",
            lockVisible: true,
            width: 44,
            minWidth: 44,
            maxWidth: 44,
            resizable: false,
            sortable: false,
            filter: false,
            suppressMovable: true,
            suppressSizeToFit: true,
            headerComponent: RunResultsMaximizeHeader,
            headerComponentParams: {
              expanded: options.expanded ?? false,
              onToggle: options.onToggleFocus,
              buttonRef: options.focusButtonRef,
            },
            cellRenderer: () => null,
          } satisfies ColDef<CompoundCurveRow>,
        ]
      : []),
  ];
}

function InterceptCell({
  display,
  data,
  options,
  primary,
}: {
  display: InterceptDisplay;
  data: CompoundCurveRow;
  options: ColumnOptions;
  primary: boolean;
}) {
  const numeric = display.kind === "scalar" || display.kind === "qualifier";
  const unit = options.unit ?? data.fitted_unit;
  const scale = doseUnitScale(data.fitted_unit, unit);
  const reported = display.reported.value;
  const text =
    numeric && reported != null
      ? `${display.kind === "qualifier" ? `${display.reported.qualifier} ` : ""}${Number((reported * scale).toPrecision(4))}`
      : display.text;
  const note =
    display.kind === "qualifier"
      ? display.reported.qualifier === "<"
        ? "Below tested range"
        : "Above tested range"
      : display.kind === "nd"
        ? "Not determined"
        : display.kind === "missing"
          ? "Recompute needed"
          : null;
  const tooltip = [
    display.tooltip,
    display.kind === "scalar"
      ? `Full precision: ${reported} ${displayDoseUnit(data.fitted_unit)}`
      : "",
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <div
      className="flex h-full flex-col items-end justify-center gap-1 whitespace-normal text-right leading-snug"
      title={tooltip || undefined}
    >
      <span
        className={`whitespace-nowrap tabular-nums ${primary ? "font-semibold" : "font-medium"} ${display.warning ? "text-amber-700 dark:text-amber-400" : "text-foreground"}`}
      >
        {text}
        {numeric && !options.unit && unit ? (
          <span className="ml-1 text-xs font-normal text-muted-foreground">
            {displayDoseUnit(unit)}
          </span>
        ) : null}
      </span>
      {note && <span className="text-xs text-muted-foreground">{note}</span>}
    </div>
  );
}

/**
 * One column per protocol intercept spec.
 *
 * The primary intercept (`intercepts[0]`) reads `row.fitted_value` — the
 * domain layer guarantees this equals `intercept_values[0].value`, and
 * legacy curves that lack any persisted `intercept_values` still expose
 * the headline value here. Sort defaults to ascending on the primary
 * (lowest = most potent).
 *
 * Secondary intercepts look up their value via `findInterceptValue` —
 * matched by `(kind, level)` so a later protocol relabel of an intercept
 * doesn't break the column→cell wiring on existing curves.
 *
 * Edge cases:
 *   - Qualified values retain their bound and show an explicit tested-range note.
 *   - Missing match → "—" with a "Recompute needed" note (the curve was
 *     fit before this intercept was added to the protocol).
 *
 * When the protocol declares no intercepts (legacy or single-intercept
 * curves), fall back to a single "Fitted Value" column so the table
 * still surfaces the headline number.
 */
function buildInterceptColumns(
  intercepts: InterceptSpec[],
  options: ColumnOptions,
): ColDef<CompoundCurveRow>[] {
  if (intercepts.length === 0) {
    return [
      {
        headerName: `Fitted value${options.unit ? ` (${displayDoseUnit(options.unit)})` : ""}`,
        field: "fitted_value",
        initialWidth: 152,
        minWidth: 144,
        initialSort: "asc",
        type: "numericColumn",
        filter: false,
        valueGetter: ({ data }) =>
          data
            ? data.fitted_value * doseUnitScale(data.fitted_unit, options.unit ?? data.fitted_unit)
            : null,
        cellStyle: { display: "flex", alignItems: "center", justifyContent: "flex-end" },
        cellRenderer: (params: ICellRendererParams<CompoundCurveRow>) => {
          if (!params.data) return null;
          return (
            <span className="tabular-nums">
              {Number(
                (
                  params.data.fitted_value *
                  doseUnitScale(params.data.fitted_unit, options.unit ?? params.data.fitted_unit)
                ).toPrecision(4),
              )}
              {!options.unit && ` ${displayDoseUnit(params.data.fitted_unit)}`}
            </span>
          );
        },
      },
    ];
  }

  return intercepts.map((spec, idx): ColDef<CompoundCurveRow> => {
    const label = interceptLabel(spec);
    return {
      headerName: `${label}${options.unit ? ` (${displayDoseUnit(options.unit)})` : ""}`,
      colId: `intercept:${spec.kind}:${spec.level}`,
      initialWidth: 144,
      minWidth: 136,
      type: "numericColumn",
      filter: false,
      // Primary intercept gets default sort: lowest fitted value is most
      // potent for IC/EC curves.
      ...(idx === 0 ? { initialSort: "asc" as const } : {}),
      // Sorting and rendering share the reported value and qualifier. View filters
      // compare the bound-aware report separately instead of sorting sentinels. Both use
      // same `formatInterceptDisplay` so the sort order matches the
      // chemist's mental model (scalar < qualifier < ND/missing) instead
      // of leaking the asymptote-bound scalar that the Hill fitter parks
      // on `fitted_value` for inactive curves.
      valueGetter: (params) => {
        if (!params.data) return null;
        const iv = findInterceptValue(params.data.intercept_values, spec);
        const value = iv?.value ?? (idx === 0 ? params.data.fitted_value : null);
        const display = formatInterceptDisplay({
          value,
          at_bound: iv?.at_bound,
          qualifier: iv?.qualifier,
          primary: idx === 0,
          curve_class: params.data.curve_class,
          ...doseRange(params.data.data_points),
        });
        return display.sortValue == null
          ? null
          : display.sortValue *
              doseUnitScale(params.data.fitted_unit, options.unit ?? params.data.fitted_unit);
      },
      cellRenderer: (params: ICellRendererParams<CompoundCurveRow>) => {
        if (!params.data) return null;
        const iv = findInterceptValue(params.data.intercept_values, spec);
        const value = iv?.value ?? (idx === 0 ? params.data.fitted_value : null);
        const display = formatInterceptDisplay({
          value,
          at_bound: iv?.at_bound,
          qualifier: iv?.qualifier,
          primary: idx === 0,
          curve_class: params.data.curve_class,
          ...doseRange(params.data.data_points),
        });
        return (
          <InterceptCell
            display={display}
            data={params.data}
            options={options}
            primary={idx === 0}
          />
        );
      },
    };
  });
}
