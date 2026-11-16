import { WorkbenchPage, sourceFromParams } from "@/features/visualization";

export default async function VisualizePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  return <WorkbenchPage source={sourceFromParams(await searchParams)} />;
}
