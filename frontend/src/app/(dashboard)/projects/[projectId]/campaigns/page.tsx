import { CampaignList } from "@/features/screen-campaign/components/campaign-list";

interface PageProps {
  params: Promise<{ projectId: string }>;
}

/**
 * Campaign list page — /projects/[projectId]/campaigns
 *
 * Server component that awaits the dynamic `params` (required by Next.js 16 +
 * React 19) before passing the resolved `projectId` into the client-side list.
 */
export default async function CampaignsPage({ params }: PageProps) {
  const { projectId } = await params;
  return (
    <div className="container py-6">
      <h1 className="mb-6 text-2xl font-semibold">Campaigns</h1>
      <CampaignList projectId={projectId} />
    </div>
  );
}
