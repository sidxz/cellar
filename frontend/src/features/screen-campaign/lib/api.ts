/**
 * Feature-local re-exports of the orval-generated campaigns module.
 *
 * Consumers import from "@/features/screen-campaign" (or this module directly)
 * rather than reaching into the generated path, so the generated path is an
 * implementation detail that can change without touching call sites.
 */
export {
  // ── Query functions ────────────────────────────────────────────────────────
  listCampaignsApiV1CampaignsGet,
  getCampaignApiV1CampaignsCampaignIdGet,
  getPublishedCampaignApiV1CampaignsCampaignIdPublishedGet,
  // ── Query key helpers ──────────────────────────────────────────────────────
  getListCampaignsApiV1CampaignsGetQueryKey,
  getListCampaignsApiV1CampaignsGetQueryOptions,
  getGetCampaignApiV1CampaignsCampaignIdGetQueryKey,
  getGetCampaignApiV1CampaignsCampaignIdGetQueryOptions,
  // ── React Query hooks (read) ───────────────────────────────────────────────
  useListCampaignsApiV1CampaignsGet,
  useGetCampaignApiV1CampaignsCampaignIdGet,
  useGetPublishedCampaignApiV1CampaignsCampaignIdPublishedGet,
  // ── Mutation functions ─────────────────────────────────────────────────────
  createCampaignApiV1CampaignsPost,
  updateCampaignApiV1CampaignsCampaignIdPatch,
  addResultsFromCollectionApiV1CampaignsCampaignIdAddFromCollectionPost,
  addResultsFromCampaignApiV1CampaignsCampaignIdAddFromCampaignPost,
  addResultsFromRunApiV1CampaignsCampaignIdAddFromRunPost,
  addCampaignChannelApiV1CampaignsCampaignIdChannelsPost,
  updateCampaignChannelApiV1CampaignsCampaignIdChannelsChannelIdPatch,
  removeCampaignChannelApiV1CampaignsCampaignIdChannelsChannelIdDelete,
  addResultRowApiV1CampaignsCampaignIdResultsPost,
  removeResultRowApiV1CampaignsCampaignIdResultsResultIdDelete,
  setResultDecisionApiV1CampaignsCampaignIdResultsResultIdPatch,
  overrideResultCellApiV1CampaignsCampaignIdResultsResultIdCellsChannelIdPatch,
  refreshCampaignApiV1CampaignsCampaignIdRefreshPost,
  closeCampaignApiV1CampaignsCampaignIdClosePost,
  supersedeCampaignApiV1CampaignsCampaignIdSupersedePost,
} from "@/shared/lib/api/campaigns/campaigns";
