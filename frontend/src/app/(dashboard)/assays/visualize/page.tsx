import { WorkbenchPage, levelFromParams, sourceFromParams } from "@/features/visualization";

export default async function VisualizePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  return <WorkbenchPage source={sourceFromParams(params)} level={levelFromParams(params)} />;
}
