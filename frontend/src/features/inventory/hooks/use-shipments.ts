"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import type {
  CreateShipmentInput,
  Shipment,
  ShipmentItem,
  ShipmentSummary,
} from "../types/shipment";

const SHIPMENTS_KEY = ["shipments"];

export function useShipments(status?: string) {
  return useQuery({
    queryKey: [...SHIPMENTS_KEY, { status }],
    queryFn: () =>
      customInstance<ShipmentSummary[]>({
        url: "/api/v1/shipments",
        method: "GET",
        params: status ? { status } : undefined,
      }),
  });
}

export function useShipment(id: string | undefined) {
  return useQuery({
    queryKey: [...SHIPMENTS_KEY, id],
    queryFn: () =>
      customInstance<Shipment>({
        url: `/api/v1/shipments/${id}`,
        method: "GET",
      }),
    enabled: !!id,
  });
}

export function useCreateShipment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateShipmentInput) =>
      customInstance<Shipment>({
        url: "/api/v1/shipments",
        method: "POST",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SHIPMENTS_KEY });
      showSuccess("Shipment created");
    },
  });
}

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
        url: `/api/v1/shipments/${id}/ship`,
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
        url: `/api/v1/shipments/${id}/in-transit`,
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
        url: `/api/v1/shipments/${id}/deliver`,
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
        url: `/api/v1/shipments/${id}/return`,
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
    mutationFn: ({
      id,
      sample_id,
      amount_value,
      amount_unit,
    }: {
      id: string;
      sample_id: string;
      amount_value: number;
      amount_unit: string;
    }) =>
      customInstance<Shipment>({
        url: `/api/v1/shipments/${id}/items`,
        method: "POST",
        data: { sample_id, amount_value, amount_unit },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SHIPMENTS_KEY });
      showSuccess("Item added to shipment");
    },
  });
}
