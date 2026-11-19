import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { PreviewBulkRegistrationResponse, PreviewCddImportBody } from "@/shared/lib/api/model";
import { useMutation } from "@tanstack/react-query";

/** POST /api/v1/cdd-import/preview — a sample of up to 20 vault molecules as an import would map them. */
export function useCddImportPreview() {
  return useMutation({
    mutationFn: (body: PreviewCddImportBody) =>
      customInstance<PreviewBulkRegistrationResponse>({
        url: `${API_V1}/cdd-import/preview`,
        method: "POST",
        data: body,
      }),
  });
}
