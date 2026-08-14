"use client";

import type {
  CreateKioskDeviceBody,
  KioskDeviceCreatedResponse,
  KioskDeviceResponse,
} from "@/shared/lib/api/model";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import { useMutation, useQueryClient } from "@tanstack/react-query";

// Aliases of the orval-generated DTOs (source of truth).
export type KioskDevice = KioskDeviceResponse;
export type CreatedKioskDevice = KioskDeviceCreatedResponse;
export type CreateKioskDeviceInput = CreateKioskDeviceBody;

const KIOSK_DEVICES_KEY = ["kiosk-devices"];

// ponytail: entity typed as KioskDevice (list shape, no token) rather than
// CreatedKioskDevice — the list endpoint never returns a token, so typing the
// list as the created-response would let a table row lie about having one.
// Create/revoke are hand-written below, each typed to what they actually return.
const hooks = createCrudHooks<KioskDevice, CreateKioskDeviceInput, never>({
  entityName: "Kiosk device",
  baseUrl: `${API_V1}/kiosk-devices`,
  queryKey: KIOSK_DEVICES_KEY,
});

export const useKioskDevices = hooks.useList;

export function useCreateKioskDevice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateKioskDeviceInput) =>
      customInstance<CreatedKioskDevice>({
        url: `${API_V1}/kiosk-devices`,
        method: "POST",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KIOSK_DEVICES_KEY });
    },
  });
}

export function useRevokeKioskDevice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ deviceId }: { deviceId: string }) =>
      customInstance<KioskDevice>({
        url: `${API_V1}/kiosk-devices/${deviceId}:revoke`,
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KIOSK_DEVICES_KEY });
      showSuccess("Device revoked");
    },
  });
}
