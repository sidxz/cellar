import { CampaignBuilder } from "@/features/screen-campaign/components/campaign-builder";

interface PageProps {
  params: Promise<{ id: string; campaignId: string }>;
}

/**
 * Server component — awaits Next.js 16 dynamic params, then renders
 * the client CampaignBuilder (draft path) or CampaignView (closed path).
 */
export default async function CampaignBuilderPage({ params }: PageProps) {
  const { id: projectId, campaignId } = await params;
  return (
    <CampaignBuilder campaignId={campaignId} projectId={projectId} />
  );
}
