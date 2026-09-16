"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  CreateShipmentInput,
  ImportPreviewResponse,
  ResolvedItem,
  Shipment,
  ShipmentItemInput,
  ShipmentLink,
  ShipmentSummary,
} from "../types/shipment";

const SHIPMENTS_KEY = ["shipments"];

const shipmentHooks = createCrudHooks<Shipment, CreateShipmentInput, Record<string, unknown>>({
  entityName: "Shipment",
  baseUrl: `${API_V1}/shipments`,
  queryKey: SHIPMENTS_KEY,
});

/** Custom list — returns ShipmentSummary[], supports optional status filter. */
export function useShipments(status?: string) {
  return useQuery({
    queryKey: [...SHIPMENTS_KEY, { status }],
    queryFn: () =>
      customInstance<ShipmentSummary[]>({
        url: `${API_V1}/shipments`,
        method: "GET",
        params: status ? { status } : undefined,
      }),
  });
}

export const useShipment = shipmentHooks.useGet;
export const useCreateShipment = shipmentHooks.useCreate;
export const useDeleteShipment = shipmentHooks.useDelete;

// --- State transitions (callers pass { id, ...payload }) ---

export function useShipShipment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      tracking_number,
      shipping_date,
    }: {
      id: string;
      tracking_number: string;
      shipping_date?: string | null;
    }) =>
      customInstance<Shipment>({
        url: `${API_V1}/shipments/${id}/ship`,
        method: "POST",
        data: { tracking_number, shipping_date },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SHIPMENTS_KEY });
      showSuccess("Shipment marked as shipped");
    },
  });
}

export function useMarkInTransit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id }: { id: string }) =>
      customInstance<Shipment>({
        url: `${API_V1}/shipments/${id}/in-transit`,
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SHIPMENTS_KEY });
      showSuccess("Shipment marked in transit");
    },
  });
}

export function useDeliverShipment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      received_date,
    }: {
      id: string;
      received_date?: string | null;
    }) =>
      customInstance<Shipment>({
        url: `${API_V1}/shipments/${id}/deliver`,
        method: "POST",
        data: { received_date },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SHIPMENTS_KEY });
      showSuccess("Shipment delivered");
    },
  });
}

export function useReturnShipment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id }: { id: string }) =>
      customInstance<Shipment>({
        url: `${API_V1}/shipments/${id}/return`,
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SHIPMENTS_KEY });
      showSuccess("Shipment returned");
    },
  });
}

export function useAddShipmentItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...item }: { id: string } & ShipmentItemInput) =>
      customInstance<Shipment>({
        url: `${API_V1}/shipments/${id}/items`,
        method: "POST",
        data: item,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SHIPMENTS_KEY });
      showSuccess("Item added to shipment");
    },
  });
}

export function useUpdateShipment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      ...data
    }: {
      id: string;
      carrier?: string | null;
      expected_arrival_date?: string | null;
      shipping_conditions?: string | null;
      notes?: string | null;
    }) =>
      customInstance<Shipment>({
        url: `${API_V1}/shipments/${id}`,
        method: "PATCH",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SHIPMENTS_KEY });
      showSuccess("Shipment updated");
    },
  });
}

export function usePreviewShipmentImport() {
  return useMutation({
    mutationFn: (
      rows: Array<{
        compound: string;
        batch: string;
        sample: string;
        amount: string;
      }>,
    ) =>
      customInstance<ImportPreviewResponse>({
        url: `${API_V1}/shipments/import/preview`,
        method: "POST",
        data: { rows },
      }),
  });
}

/** POST /shipments/resolve-items — barcodes → plate / sample items, input order kept. */
export function useResolveShipmentItems() {
  return useMutation({
    mutationFn: (barcodes: string[]) =>
      customInstance<ResolvedItem[]>({
        url: `${API_V1}/shipments/resolve-items`,
        method: "POST",
        data: { barcodes },
      }),
  });
}

/** GET /{plates|samples|plate-loans}/{id}/shipments, newest first. Keyed under
 * SHIPMENTS_KEY so every shipment mutation above already refreshes these cards. */
function useShipmentLinks(path: "plates" | "samples" | "plate-loans", id: string | undefined) {
  return useQuery({
    queryKey: [...SHIPMENTS_KEY, "links", path, id],
    queryFn: ({ signal }) =>
      customInstance<ShipmentLink[]>({
        url: `${API_V1}/${path}/${id}/shipments`,
        method: "GET",
        signal,
      }),
    enabled: !!id,
  });
}

export const useShipmentsForPlate = (plateId: string | undefined) =>
  useShipmentLinks("plates", plateId);
export const useShipmentsForSample = (sampleId: string | undefined) =>
  useShipmentLinks("samples", sampleId);
export const useShipmentsForLoan = (loanId: string | undefined) =>
  useShipmentLinks("plate-loans", loanId);
