import { type CategoryColor, resolveCategoryColor } from "@/shared/lib/category-colors";
import type { Project } from "../types";

/**
 * Stable visual identity color for a project folder card.
 *
 * v1: a stable hash of the project name (same color every visit). Tag-based
 * override slots in here once project tags ship in the projects list payload —
 * pass the tag's hex as the second arg to resolveCategoryColor.
 */
export function projectIdentityColor(project: Project): CategoryColor {
  return resolveCategoryColor(project.name);
}
