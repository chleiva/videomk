// Share a video by link (docs/SHARE_PREVIEWS_2026-11-28.md): the owner opts in per video and can take the link back.
// The share API lives in its own small stack; its address is a build-time setting (PUBLIC_SHARE_API_BASE). Empty: the feature is hidden.
import { getAuthorizationHeader } from "./auth";
import { currentLocaleHeaders } from "./i18n";

const env = (import.meta as any).env ?? {};
export const SHARE_API_BASE: string = String(env.PUBLIC_SHARE_API_BASE || "").replace(/\/+$/, "");

export type ShareState = { shared: false } | { shared: true; url: string };
export type ShareResult = { ok: true; state: ShareState } | { ok: false; kind: "unavailable" | "not_ready" | "auth" | "error" };

export const shareAvailable = (base: string = SHARE_API_BASE): boolean => /^https:\/\//.test(base);

export const shareUrlFor = (userId: string, videoId: string, base: string = SHARE_API_BASE) => `${base}/users/${encodeURIComponent(userId)}/videos/${encodeURIComponent(videoId)}/share`;

/** A public share address is only ever an https address with a 22 character token (never anything else the server might say). */
export const isShareUrl = (u: unknown): u is string => typeof u === "string" && /^https:\/\/[a-z0-9.-]+\/[A-Za-z0-9_-]{22}$/.test(u);

/** Maps an answer of the share API (pure). */
export function mapShareAnswer(status: number, body: any): ShareResult {
  if (status === 200 && body?.shared === true && isShareUrl(body.url)) return { ok: true, state: { shared: true, url: body.url } };
  if (status === 200 && body?.shared === false) return { ok: true, state: { shared: false } };
  if (status === 409) return { ok: false, kind: "not_ready" };
  if (status === 401 || status === 403) return { ok: false, kind: "auth" };
  return { ok: false, kind: "error" };
}

async function call(method: "GET" | "POST" | "DELETE", videoId: string, base: string = SHARE_API_BASE): Promise<ShareResult> {
  if (!shareAvailable(base)) return { ok: false, kind: "unavailable" };
  try {
    const { Authorization, userId } = await getAuthorizationHeader();
    if (!userId) return { ok: false, kind: "auth" };
    const res = await fetch(shareUrlFor(userId, videoId, base), { method, headers: { "Content-Type": "application/json", Authorization, ...currentLocaleHeaders() } });
    let body: any = null;
    try { body = await res.json(); } catch { /* no body */ }
    return mapShareAnswer(res.status, body);
  } catch {
    return { ok: false, kind: "error" };
  }
}

export const getShare = (videoId: string) => call("GET", videoId);
export const createShare = (videoId: string) => call("POST", videoId);
export const revokeShare = async (videoId: string): Promise<ShareResult> => {
  const r = await call("DELETE", videoId);
  return r.ok ? { ok: true, state: { shared: false } } : r;
};
