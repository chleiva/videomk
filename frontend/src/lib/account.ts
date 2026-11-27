// Account deletion from the settings page (contract: docs/ACCOUNT_DELETION.md). The pure parts (token age, answer mapping, what is wiped locally) are tested in account.test.ts.
import { getAuthorizationHeader, signOut } from "./auth";
import { API_BASE, AUTH_DOMAIN, COGNITO_CLIENT_ID } from "./config";
import { currentLocaleHeaders } from "./i18n";

/** The word the person types. */
export const CONFIRM_WORD = "DELETE";
/** A deletion needs a sign-in at most this old (seconds): the server answers 401 reauth_required otherwise. */
export const MAX_AUTH_AGE_S = 600;
/** Where the deletion resumes after the person signed in again (read by the sign-in page; same-origin paths only). */
export const RESUME_KEY = "vmk_resume";
export const RESUME_PATH = "/settings?delete=1";
const RESUME_TTL_MS = 15 * 60 * 1000;
const CONFIRMED_KEY = "vmk_delete_confirmed";

const urlFor = (userId: string, tail: string) => `${API_BASE}/users/${encodeURIComponent(userId)}/account/${tail}`;

/** The `auth_time` claim (epoch seconds) of an id token, or null. */
export function authTimeOf(idToken: string | null | undefined): number | null {
  try {
    const payload = JSON.parse(atob(String(idToken).split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return typeof payload.auth_time === "number" ? payload.auth_time : null;
  } catch {
    return null;
  }
}

/** Was the sign-in recent enough for the server to accept a deletion? An unreadable token counts as not fresh. */
export function isFreshSignIn(idToken: string | null | undefined, nowMs: number = Date.now(), maxAgeS: number = MAX_AUTH_AGE_S): boolean {
  const at = authTimeOf(idToken);
  return at !== null && nowMs / 1000 - at <= maxAgeS;
}

/** The typed word counts when it is exactly DELETE, ignoring case and surrounding space (the server only ever sees the constant). */
export const confirmationOk = (typed: string): boolean => typed.trim().toUpperCase() === CONFIRM_WORD;

export type AppleStep = "not_linked" | "revoke_available" | "revoke_off" | "unknown";
export type DeleteResult =
  | { ok: true; apple: AppleStep }
  | { ok: false; kind: "reauth" | "network" | "error" | "auth" };

/** Maps the delete answer to what the page does next (pure: the response is read by the caller). */
export function mapDeleteAnswer(status: number, body: any): DeleteResult {
  if (status === 202) {
    const a = body?.apple;
    return { ok: true, apple: a === "revoke_available" || a === "revoke_off" || a === "not_linked" ? a : "unknown" };
  }
  if (status === 401 && body?.code === "reauth_required") return { ok: false, kind: "reauth" };
  if (status === 401 || status === 403) return { ok: false, kind: "auth" };
  return { ok: false, kind: "error" };
}

/** POST /users/{id}/account/delete. Idempotent on the server, so a retry is safe. */
export async function requestDeletion(): Promise<DeleteResult> {
  const { Authorization, userId } = await getAuthorizationHeader();
  if (!userId) return { ok: false, kind: "auth" };
  try {
    const res = await fetch(urlFor(userId, "delete"), { method: "POST", headers: { "Content-Type": "application/json", Authorization, ...currentLocaleHeaders() }, body: JSON.stringify({ confirm: CONFIRM_WORD }) });
    let body: any = {};
    try { body = await res.json(); } catch { /* no body */ }
    return mapDeleteAnswer(res.status, body);
  } catch {
    return { ok: false, kind: "network" };
  }
}

/** Sign in with Apple grant: the link to open (Apple's page), or null (then the person gets the manual instruction). */
export async function appleRevokeUrl(): Promise<string | null> {
  const { Authorization, userId } = await getAuthorizationHeader();
  if (!userId) return null;
  try {
    const res = await fetch(urlFor(userId, "apple-revoke"), { method: "POST", headers: { "Content-Type": "application/json", Authorization, ...currentLocaleHeaders() }, body: JSON.stringify({ return: "web" }) });
    if (!res.ok) return null;
    const u = (await res.json())?.authorize_url;
    return typeof u === "string" && u.startsWith("https://appleid.apple.com/") ? u : null;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------- signing in again (the 10 minute rule)

/** Remember that the deletion resumes on the settings page after a fresh sign-in (15 minutes). */
export function rememberResume(nowMs: number = Date.now()): void {
  try {
    localStorage.setItem(RESUME_KEY, JSON.stringify({ path: RESUME_PATH, at: nowMs }));
    sessionStorage.setItem(CONFIRMED_KEY, "1");
  } catch { /* private mode: the person starts again from settings */ }
}

/** The pending path when it is fresh, else null. Only our own path is ever returned (never an open redirect). */
export function readResume(raw: string | null | undefined, nowMs: number = Date.now()): string | null {
  try {
    const v = JSON.parse(String(raw));
    return v && v.path === RESUME_PATH && typeof v.at === "number" && nowMs - v.at >= 0 && nowMs - v.at <= RESUME_TTL_MS ? RESUME_PATH : null;
  } catch {
    return null;
  }
}

export const wasConfirmed = (): boolean => { try { return sessionStorage.getItem(CONFIRMED_KEY) === "1"; } catch { return false; } };
export function clearResume(): void { try { localStorage.removeItem(RESUME_KEY); sessionStorage.removeItem(CONFIRMED_KEY); } catch { /* nothing to clear */ } }

/**
 * End the hosted page's own session, then land on the sign-in page, so the next sign-in is a real one with a new `auth_time`
 * (the classic hosted UI ignores `prompt=login`, docs/ACCOUNT_DELETION.md section 2). Never resolves.
 */
export function signInAgain(): Promise<never> {
  rememberResume();
  signOut();
  const back = `${location.origin}/`;
  location.assign(`${AUTH_DOMAIN}/logout?client_id=${encodeURIComponent(COGNITO_CLIENT_ID)}&logout_uri=${encodeURIComponent(back)}`);
  return new Promise<never>(() => {});
}

// ---------------------------------------------------------------- what leaves this browser

/** Our keys that survive a deletion: the language and the look are the device's, not the person's. */
const KEEP = new Set(["vmk_locale", "vmk_theme"]);
/** Every key of this site that belongs to the person (tokens, caches, drafts, preferences). Pure, so it is tested. */
export function keysToWipe(keys: readonly string[]): string[] {
  return keys.filter((k) => !KEEP.has(k) && (k.startsWith("vmk_") || k.startsWith("vmk-") || k.startsWith("videomk")));
}

/** Clears the person's local data: tokens, session caches, drafts, saved prompts, preferences. */
export function wipeLocalData(): void {
  try {
    const keys: string[] = [];
    for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); if (k) keys.push(k); }
    keysToWipe(keys).forEach((k) => localStorage.removeItem(k));
  } catch { /* nothing to clear */ }
  try { sessionStorage.clear(); } catch { /* nothing to clear */ }
  signOut();
}
