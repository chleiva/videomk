import { getAuthorizationHeader } from "./auth";
import { apiGateway } from "./config";
import { currentLocaleHeaders, t } from "./i18n";
import { parseLookAnswer } from "./looks";
import type { LookAnswer } from "./looks";
import { cancelOutcome } from "./videos";
import type { CancelOutcome } from "./videos";
import { parsePlanState, planRefusal } from "./plan";
import type { PlanState } from "./plan";

export type StartResult =
  | { ok: true; videoId: string; look?: LookAnswer | null }   // `look.note`: the server adapted the chosen look (shown as one line while the video is made)
  | { ok: false; kind: "invalid" | "quota" | "auth" | "error" | "credits" | "blocked" | "paused" | "plan"; message: string; balance?: number; needed?: number; code?: string; requiresPlan?: string | null; canUpgrade?: boolean };

/** What `generate` answered, as the form needs it (pure: tested). A plan refusal (403 plan_*, 429 free_budget_spent) carries the server's own sentence and is never mistaken for an expired session. */
export function startOutcome(status: number, body: any): StartResult {
  body = body && typeof body === "object" ? body : {};
  if (status >= 200 && status < 300) return { ok: true, videoId: String(body.video_id || ""), look: parseLookAnswer(body) };
  if (status === 402) return { ok: false, kind: "credits", message: body.message || t("api.no_credits"), balance: typeof body.balance === "number" ? body.balance : undefined, needed: typeof body.needed === "number" ? body.needed : undefined };
  const plan = planRefusal(status, body);
  if (plan) return { ok: false, kind: "plan", message: plan.message || t("api.start_failed"), code: plan.code, requiresPlan: plan.requiresPlan, canUpgrade: plan.canUpgrade };
  if (status === 400 && body.status === "blocked") return { ok: false, kind: "blocked", message: body.message || t("create.blocked_fallback") };
  if (status === 429 && body.status === "paused") return { ok: false, kind: "paused", message: body.message || t("create.paused_fallback") };
  if (status === 400 || status === 409) return { ok: false, kind: "invalid", message: body.message || t("api.invalid"), code: typeof body.code === "string" ? body.code : typeof body.error === "string" ? body.error : undefined };
  if (status === 429) return { ok: false, kind: "quota", message: body.message || t("api.quota") };
  if (status === 401 || status === 403) return { ok: false, kind: "auth", message: t("api.session_expired") };
  return { ok: false, kind: "error", message: t("api.start_failed") };
}

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
  return startOutcome(res.status, body);
}

export function newRequestId(): string {
  return (globalThis.crypto?.randomUUID?.() as string) || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export interface Wallet { balance: number; unlimited: boolean; buckets: { kind: string; remaining: number; expires_at: number | null }[]; next_daily_at: number | null; plans?: PlanState }

export function parseWallet(b: any): Wallet | null {
  if (typeof b?.balance !== "number") return null;
  const plans = parsePlanState(b);
  return { balance: b.balance, unlimited: b.unlimited === true, buckets: Array.isArray(b.buckets) ? b.buckets : [], next_daily_at: typeof b.next_daily_at === "number" ? b.next_daily_at : null, ...(plans.plan || plans.free ? { plans } : {}) };
}

/** The person's credits (GET .../wallet). null when it cannot be read: callers then simply leave the balance out. */
export async function getWallet(): Promise<Wallet | null> {
  try {
    const { Authorization, userId } = await getAuthorizationHeader();
    if (!userId) return null;
    const res = await fetch(apiGateway.wallet(userId), { headers: { Authorization, ...currentLocaleHeaders(), "X-Timezone": Intl.DateTimeFormat().resolvedOptions().timeZone } });
    if (!res.ok) return null;
    return parseWallet(await res.json());
  } catch {
    return null;
  }
}

/** Cancel a video that is being made (POST .../cancel, docs/CREATE_API.md): the workflow stops and the credits of this attempt come back; a second call is harmless.
 *  `try_again` (the video moved a step between the server's read and write) is answered by sending the same call once more. */
export async function cancelVideo(videoId: string): Promise<CancelOutcome> {
  try {
    const { Authorization, userId } = await getAuthorizationHeader();
    if (!userId) return { ok: false, kind: "error" };
    const call = async () => { const res = await fetch(apiGateway.cancelVideo(userId, videoId), { method: "POST", headers: { Authorization, ...currentLocaleHeaders() } }); return cancelOutcome(res.status, await res.json().catch(() => null)); };
    const out = await call();
    return !out.ok && out.kind === "try_again" ? await call() : out;
  } catch { return { ok: false, kind: "error" }; }
}
