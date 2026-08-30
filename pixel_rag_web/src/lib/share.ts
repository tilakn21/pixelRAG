// pixel_rag_web/src/lib/share.ts
/**
 * Sharing photos out of PixelRAG.
 *
 * There is no WhatsApp API a web page can post images to — `wa.me` links carry
 * text only. The one route that hands real image files to WhatsApp is the OS
 * share sheet via the Web Share API, so that is the primary path and everything
 * else is an honest fallback:
 *
 *   1. Share sheet with the actual files  → WhatsApp, AirDrop, Messages, Mail
 *   2. Download the photos + open WhatsApp → you attach them yourself
 *
 * Two constraints drive the shape of this module:
 *
 *   • `navigator.share` requires a *secure context*. `localhost` counts;
 *     `http://192.168.x.x` does not. So on the Mac you get the share sheet, and
 *     on a phone hitting the Mac over plain HTTP you get the download path.
 *
 *   • The share call must happen inside the user gesture. Awaiting several MB
 *     of fetches first and *then* calling `navigator.share` throws
 *     NotAllowedError in Safari. Files are therefore loaded up front and the
 *     share call itself does no awaiting.
 */

import { getPhotoUrl } from "./api";

/** Share sheets get unhappy well before this; WhatsApp itself caps at 30. */
export const MAX_SHARE_FILES = 20;

export interface ShareAvailability {
  /** The share sheet can be used right now. */
  available: boolean;
  /** Why not, in words meant for the user. */
  reason: string | null;
}

export function shareAvailability(): ShareAvailability {
  if (typeof navigator === "undefined" || typeof window === "undefined") {
    return { available: false, reason: "Not available before the page loads." };
  }
  if (typeof navigator.share !== "function" || typeof navigator.canShare !== "function") {
    return { available: false, reason: "This browser has no share sheet." };
  }
  if (!window.isSecureContext) {
    return {
      available: false,
      reason:
        "The share sheet needs a secure connection. Over plain http on the " +
        "network (a phone reaching this Mac by IP) browsers disable it.",
    };
  }
  return { available: true, reason: null };
}

/**
 * Fetch the selected photos as File objects.
 *
 * Originals, not resized copies: the resize endpoint emits WebP, and iOS
 * WhatsApp treats a .webp as a sticker rather than a photo. Sharing is a
 * handful of images at a time, so the extra bytes cost nothing that matters.
 */
export async function loadPhotoFiles(
  photoIds: number[],
  libHash: string | undefined,
  onProgress?: (done: number, total: number) => void
): Promise<File[]> {
  const ids = photoIds.slice(0, MAX_SHARE_FILES);
  const files: File[] = [];
  let done = 0;

  for (const id of ids) {
    try {
      const res = await fetch(getPhotoUrl(id, libHash));
      if (!res.ok) continue;
      const blob = await res.blob();
      const ext = (blob.type.split("/")[1] || "jpg").replace("jpeg", "jpg");
      files.push(new File([blob], `pixelrag-${id}.${ext}`, { type: blob.type }));
    } catch {
      /* one unreadable photo should not sink the whole share */
    } finally {
      done += 1;
      onProgress?.(done, ids.length);
    }
  }
  return files;
}

/** Whether these specific files can go to the share sheet. */
export function canShareFiles(files: File[]): boolean {
  if (!shareAvailability().available || files.length === 0) return false;
  try {
    return navigator.canShare({ files });
  } catch {
    return false;
  }
}

/**
 * Hand the files to the OS. Call this straight from a click handler — no await
 * before it, or Safari will reject it as gestureless.
 */
export async function shareFiles(files: File[], text: string): Promise<"shared" | "cancelled"> {
  try {
    await navigator.share(text ? { files, text } : { files });
    return "shared";
  } catch (e) {
    // AbortError just means the user dismissed the sheet — not a failure.
    if (e instanceof DOMException && e.name === "AbortError") return "cancelled";
    throw e;
  }
}

/** WhatsApp with a caption prefilled and a contact picker. Text only — WhatsApp
 *  has no mechanism for a link to carry images. */
export function openWhatsApp(text: string) {
  const url = text
    ? `https://wa.me/?text=${encodeURIComponent(text)}`
    : "https://wa.me/";
  window.open(url, "_blank", "noopener,noreferrer");
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  // Revoke on the next tick; revoking immediately cancels the download in Safari.
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
