import { useMDXComponents as getThemeComponents } from "nextra-theme-docs";

// Chemistry widgets are exposed globally to MDX so writers can embed them
// without an explicit import in every page. All are client-only (ssr:false).
import { DoseResponseExplorer } from "./components/DoseResponseExplorer";
import { PlateHeatmapDemo } from "./components/PlateHeatmapDemo";
import { PropertyCalculator } from "./components/PropertyCalculator";
import { SimilarityDemo } from "./components/SimilarityDemo";
import { SmilesAnnotator } from "./components/SmilesAnnotator";
import { StructureViewer } from "./components/StructureViewer";

const themeComponents = getThemeComponents();

export function useMDXComponents(components?: Record<string, unknown>) {
  return {
    ...themeComponents,
    StructureViewer,
    PropertyCalculator,
    DoseResponseExplorer,
    PlateHeatmapDemo,
    SimilarityDemo,
    SmilesAnnotator,
    ...components,
  };
}
