import { SavedViewPage, levelFromParams, sourceFromParams } from "@/features/visualization";

export default async function SavedVisualizationPage({
  params,
  searchParams,
}: {
  params: Promise<{ viewId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const [{ viewId }, query] = await Promise.all([params, searchParams]);
  // Source and level in the query string override the view's saved ones.
  return (
    <SavedViewPage
      viewId={viewId}
      sourceOverride={sourceFromParams(query)}
      levelOverride={query.level ? levelFromParams(query) : null}
    />
  );
}
