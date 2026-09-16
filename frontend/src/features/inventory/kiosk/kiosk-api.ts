import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type {
  KioskConfirmBody,
  KioskConfirmResponse,
  KioskScanResponse,
} from "@/shared/lib/api/model";

export const KIOSK_TOKEN_KEY = "kiosk.token";

export function readKioskToken(): string | null {
  try {
    return window.localStorage.getItem(KIOSK_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function writeKioskToken(token: string | null): void {
  try {
    if (token) window.localStorage.setItem(KIOSK_TOKEN_KEY, token);
    else window.localStorage.removeItem(KIOSK_TOKEN_KEY);
  } catch {
    /* storage unavailable — the token lives only in memory for this page load */
  }
}

const headersFor = (token: string) => ({ "X-Kiosk-Token": token });

export function kioskScan(token: string, barcode: string): Promise<KioskScanResponse> {
  return customInstance<KioskScanResponse>({
    url: `${API_V1}/kiosk/scan`,
    method: "POST",
    data: { barcode },
    headers: headersFor(token),
  });
}

export function kioskConfirm(token: string, body: KioskConfirmBody): Promise<KioskConfirmResponse> {
  return customInstance<KioskConfirmResponse>({
    url: `${API_V1}/kiosk/confirm`,
    method: "POST",
    data: body,
    headers: headersFor(token),
  });
}
