import { WorkbenchPage, levelFromParams, sourceFromParams } from "@/features/visualization";
import { SavedViewsListPage } from "@/features/visualization/components/saved-views-list";

/** The workbench on the URL's source; with none, the list of saved views. */
export default async function VisualizePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const source = sourceFromParams(params);
  if (!source) return <SavedViewsListPage />;
  return <WorkbenchPage source={source} level={levelFromParams(params)} />;
}
