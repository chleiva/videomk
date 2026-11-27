// The account's plan as capabilities and the wallet report it (docs/CREATE_API.md "Plans", docs/PLANS.md section 5). Read-only today: nothing can be bought
// (`can_upgrade` is false), so the web shows the plan's name and limits and never a buy button. Every field is optional: a server without plans sends none of
// this and the app works as before. Pure functions (tested in plan.test.ts); the one network call (the public gallery) is at the end.
import { API_BASE } from "./config";
import { currentLocaleHeaders } from "./i18n";

export interface PlanInfo { id: string; name: string; maxSeconds: number | null; resolutions: string[]; names: Record<string, string> }
export interface FreeInfo { available: boolean; reason?: string; message?: string; resumesAt?: string }
export interface PlanState { plan: PlanInfo | null; free: FreeInfo | null; freeCreation: string | null; canUpgrade: boolean }
export const NO_PLAN: PlanState = { plan: null, free: null, freeCreation: null, canUpgrade: false };

const text = (v: unknown, max = 200): string | undefined => { const s = typeof v === "string" ? v.trim() : ""; return s ? s.slice(0, max) : undefined; };
const cap = (id: string) => id.charAt(0).toUpperCase() + id.slice(1);

/** The plan fields shared by capabilities and the wallet. Anything missing or malformed is simply absent. */
export function parsePlanState(body: unknown): PlanState {
  const b = body as any;
  if (!b || typeof b !== "object") return NO_PLAN;
  const p = b.plan && typeof b.plan === "object" ? b.plan : null;
  const id = text(p?.id, 40);
  const names: Record<string, string> = {};
  for (const x of Array.isArray(p?.plans) ? p.plans : Array.isArray(b.plans) ? b.plans : []) { const pid = text(x?.id, 40), pn = text(x?.name, 40); if (pid && pn) names[pid] = pn; }
  const max = Number(p?.limits?.max_seconds);
  const plan: PlanInfo | null = id ? {
    id, name: text(p.name, 40) ?? cap(id), maxSeconds: Number.isFinite(max) && max > 0 ? max : null,
    resolutions: Array.isArray(p?.limits?.resolutions) ? p.limits.resolutions.filter((r: unknown) => typeof r === "string") : [], names,
  } : null;
  const f = b.free && typeof b.free === "object" ? b.free : null;
  const free: FreeInfo | null = f ? { available: f.available !== false, reason: text(f.reason, 40), message: text(f.message, 300), resumesAt: text(f.resumes_at, 40) } : null;
  return { plan, free, freeCreation: text(b.free_creation, 20) ?? null, canUpgrade: b.can_upgrade === true };
}

/** "Pro" for "pro": the server's name for the plan when it listed the plans, else the id with a capital. Null in, null out. */
export function planName(state: PlanState | undefined, id: string | null | undefined): string | null {
  if (!id) return null;
  return state?.plan?.names[id] ?? (state?.plan?.id === id ? state.plan.name : cap(id));
}

// ---------------------------------------------------------------- lengths the plan forbids (`lengths.plan_max_seconds`, `lengths.locked`)
export interface LengthLock { over_seconds: number; max_seconds: number; requires_plan: string | null }
export interface LengthLimits { planMaxSeconds: number | null; locked: LengthLock[] }
export function parseLengthLimits(lengths: unknown): LengthLimits {
  const l = lengths as any;
  const max = Number(l?.plan_max_seconds ?? (Number.isFinite(Number(l?.plan_max_minutes)) ? Number(l.plan_max_minutes) * 60 : NaN));
  const locked: LengthLock[] = (Array.isArray(l?.locked) ? l.locked : []).flatMap((x: any): LengthLock[] => {
    const over = Number(x?.over_seconds), top = Number(x?.max_seconds);
    return Number.isFinite(over) && over >= 0 ? [{ over_seconds: over, max_seconds: Number.isFinite(top) && top > over ? top : Infinity, requires_plan: text(x.requires_plan, 40) ?? null }] : [];
  }).sort((a: LengthLock, b: LengthLock) => a.over_seconds - b.over_seconds);
  return { planMaxSeconds: Number.isFinite(max) && max > 0 ? max : null, locked };
}
/** Is a length of `minutes` over the plan's longest video? Returns the cheapest plan that makes it (null when the server did not say), or false when it is allowed. */
export function lengthLock(minutes: number, lim: LengthLimits | undefined): { requires: string | null } | false {
  if (!lim) return false;
  const s = minutes * 60;
  const max = lim.planMaxSeconds ?? (lim.locked.length ? lim.locked[0].over_seconds : null);
  if (max == null || s <= max + 1e-6) return false;
  const row = lim.locked.find((x) => s > x.over_seconds + 1e-6 && s <= x.max_seconds + 1e-6) ?? lim.locked.filter((x) => s > x.over_seconds + 1e-6).pop();
  return { requires: row?.requires_plan ?? null };
}

// ---------------------------------------------------------------- refusals of generate and retry that come from the plan (nothing was charged)
const PLAN_403 = new Set(["plan_length", "plan_resolution", "plan_photos", "plan_watermark", "watermark_premium", "watermark_required", "free_not_available", "device_not_verified"]);
const PLAN_429 = new Set(["free_budget_spent", "free_monthly_cap"]);
export interface PlanRefusal { code: string; message?: string; requiresPlan: string | null; canUpgrade: boolean }
/** A 403 `plan_*` / `free_not_available` or a 429 `free_budget_spent` / `free_monthly_cap`: the server's own sentence is shown in place and the draft stays. Null for anything else. */
export function planRefusal(status: number, body: unknown): PlanRefusal | null {
  const b = body as any, code = typeof b?.code === "string" ? b.code : "";
  if (!((status === 403 && (PLAN_403.has(code) || code.startsWith("plan_"))) || (status === 429 && PLAN_429.has(code)))) return null;
  return { code, message: text(b.message, 300), requiresPlan: text(b.requires_plan, 40) ?? null, canUpgrade: b.can_upgrade === true };
}

// ---------------------------------------------------------------- Create for an account that cannot make a video right now
export interface CreateLock { message?: string; reason?: string; resumesAt?: string }
/** A Free account whose free creation is off, app-only, used up or paused, and that has no credit to spend, sees the server's sentence and the showcase instead of a
 *  form that can only fail (docs/PLANS.md section 3; the same rule as the apps' CreateGate). Null: Create works as usual. */
export function createLock(wallet: { balance: number; unlimited: boolean; plans?: PlanState } | null | undefined, caps: PlanState | undefined): CreateLock | null {
  if (wallet?.unlimited) return null;
  const free = wallet?.plans?.free ?? caps?.free ?? null;
  const plan = wallet?.plans?.plan ?? caps?.plan ?? null;
  const off = (wallet?.plans?.freeCreation ?? caps?.freeCreation) === "none";
  if (plan && plan.id !== "free") return null;
  if (!(free ? !free.available : off && !!plan)) return null;
  if ((wallet?.balance ?? 0) > 0) return null;   // credits that can be spent here: Create works
  return { message: free?.message, reason: free?.reason ?? (off ? "off" : undefined), resumesAt: free?.resumesAt };
}

// ---------------------------------------------------------------- the showcase (`GET /gallery`, public): what a locked Create shows instead of an empty form
export interface GalleryVideo { id: string; title: string; video_url: string; poster_url: string | null; aspect: string | null; seconds: number | null }
const https = (v: unknown): string | null => (typeof v === "string" && /^https:\/\/[^\s"'<>]+$/.test(v) ? v : null);
export function parseGallery(body: unknown): GalleryVideo[] {
  const list = (body as any)?.videos;
  return (Array.isArray(list) ? list : []).flatMap((v: any): GalleryVideo[] => {
    const id = text(v?.id, 80), url = https(v?.video_url);
    return id && url ? [{ id, title: text(v.title, 120) ?? "", video_url: url, poster_url: https(v.poster_url), aspect: typeof v.aspect === "string" && /^\d+:\d+$/.test(v.aspect) ? v.aspect : null, seconds: typeof v.seconds === "number" && v.seconds > 0 ? v.seconds : null }] : [];
  }).slice(0, 12);
}
/** The links last an hour, so the list is fetched when it is shown and never stored. An error or an empty list is simply no showcase. */
export async function getGallery(): Promise<GalleryVideo[]> {
  try {
    const res = await fetch(`${API_BASE}/gallery`, { headers: currentLocaleHeaders() });
    return res.ok ? parseGallery(await res.json()) : [];
  } catch { return []; }
}
