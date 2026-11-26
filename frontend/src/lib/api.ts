import { getAuthorizationHeader } from "./auth";
import { apiGateway } from "./config";
import { currentLocaleHeaders, t } from "./i18n";

export type StartResult =
  | { ok: true; videoId: string }
  | { ok: false; kind: "invalid" | "quota" | "auth" | "error" | "credits" | "blocked" | "paused"; message: string; balance?: number; needed?: number; code?: string };

/** Start a generation. Returns a typed result so the UI can say what actually went wrong. */
export async function startGeneration(prompt: string, clientRequestId: string, extra: Record<string, unknown> = {}): Promise<StartResult> {
  const { Authorization, userId } = await getAuthorizationHeader();
  if (!userId) return { ok: false, kind: "auth", message: t("api.signin_required") };
  let res: Response;
  try {
    res = await fetch(apiGateway.generateVideo(userId), {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization, ...currentLocaleHeaders() },
      body: JSON.stringify({ ...extra, ...(prompt || !extra.deck ? { prompt } : {}), client_request_id: clientRequestId }), // a deck video may have no prompt: it is optional there
    });
  } catch {
    return { ok: false, kind: "error", message: t("api.network") };
  }
  let body: any = {};
  try {
    body = await res.json();
  } catch {}
  if (res.ok) return { ok: true, videoId: String(body.video_id || "") };
  if (res.status === 402) return { ok: false, kind: "credits", message: body.message || t("api.no_credits"), balance: typeof body.balance === "number" ? body.balance : undefined, needed: typeof body.needed === "number" ? body.needed : undefined };
  if (res.status === 400 && body.status === "blocked") return { ok: false, kind: "blocked", message: body.message || t("create.blocked_fallback") };
  if (res.status === 429 && body.status === "paused") return { ok: false, kind: "paused", message: body.message || t("create.paused_fallback") };
  if (res.status === 400 || res.status === 409) return { ok: false, kind: "invalid", message: body.message || t("api.invalid"), code: typeof body.code === "string" ? body.code : typeof body.error === "string" ? body.error : undefined };
  if (res.status === 429)
    return { ok: false, kind: "quota", message: body.message || t("api.quota") };
  if (res.status === 401 || res.status === 403)
    return { ok: false, kind: "auth", message: t("api.session_expired") };
  return { ok: false, kind: "error", message: t("api.start_failed") };
}

export function newRequestId(): string {
  return (globalThis.crypto?.randomUUID?.() as string) || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export interface Wallet { balance: number; unlimited: boolean; buckets: { kind: string; remaining: number; expires_at: number | null }[]; next_daily_at: number | null }

/** The person's credits (GET .../wallet). null when it cannot be read: callers then simply leave the balance out. */
export async function getWallet(): Promise<Wallet | null> {
  try {
    const { Authorization, userId } = await getAuthorizationHeader();
    if (!userId) return null;
    const res = await fetch(apiGateway.wallet(userId), { headers: { Authorization, ...currentLocaleHeaders(), "X-Timezone": Intl.DateTimeFormat().resolvedOptions().timeZone } });
    if (!res.ok) return null;
    const b = await res.json();
    if (typeof b?.balance !== "number") return null;
    return { balance: b.balance, unlimited: b.unlimited === true, buckets: Array.isArray(b.buckets) ? b.buckets : [], next_daily_at: typeof b.next_daily_at === "number" ? b.next_daily_at : null };
  } catch {
    return null;
  }
}
