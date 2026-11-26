// Cognito Hosted UI, Authorization Code + PKCE. Tokens live in localStorage (static site, no
// server to hold them). That makes XSS the main risk: keep third-party scripts out of the pages
// and consider moving to a BFF/HttpOnly-cookie flow later.
import { AUTH_APPLE, AUTH_DOMAIN, AUTH_GOOGLE, COGNITO_CLIENT_ID } from "./config";
import { buildAuthorizeUrl, parseProvider, safeReturnPath, sanitizeAuthError, shouldRetry, socialEnabled } from "./authUrl";
import type { Provider } from "./authUrl";
import { getLocale } from "./i18n";

const K = {
  tokens: "vmk_auth_tokens",
  verifier: "vmk_pkce_verifier",
  state: "vmk_auth_state",
  redirect: "vmk_post_login_redirect",
  provider: "vmk_auth_provider", // not secret: lets the one automatic retry repeat the same request
  retry: "vmk_auth_retried", // sessionStorage: loop guard for the one automatic retry
} as const;

/** An error whose message is already sanitised and safe to show to the user. */
export class AuthDisplayError extends Error {}

export const SIGNIN_PATH = "/signin/index.html";

export interface Tokens {
  access_token: string;
  id_token: string;
  refresh_token?: string;
  expires_at: number; // epoch ms
}

const SKEW_MS = 60_000;

function redirectUri(): string {
  return location.hostname === "localhost"
    ? "http://localhost:4321/auth/callback"
    : `${location.origin}/auth/callback/index.html`;
}

function b64url(bytes: ArrayBuffer | Uint8Array): string {
  const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let s = "";
  arr.forEach((b) => (s += String.fromCharCode(b)));
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function randomString(bytes = 32): string {
  return b64url(crypto.getRandomValues(new Uint8Array(bytes)));
}

async function challengeFor(verifier: string): Promise<string> {
  return b64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)));
}

function readTokens(): Tokens | null {
  try {
    const raw = localStorage.getItem(K.tokens);
    return raw ? (JSON.parse(raw) as Tokens) : null;
  } catch {
    return null;
  }
}

function writeTokens(t: Tokens) {
  localStorage.setItem(K.tokens, JSON.stringify(t));
}

export function signOut() {
  localStorage.removeItem(K.tokens);
}

async function tokenRequest(params: Record<string, string>): Promise<any> {
  const res = await fetch(`${AUTH_DOMAIN}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ client_id: COGNITO_CLIENT_ID, ...params }).toString(),
  });
  if (!res.ok) throw new Error(`token request failed: ${res.status}`);
  return res.json();
}

function toTokens(json: any, previous?: Tokens | null): Tokens {
  return {
    access_token: json.access_token,
    id_token: json.id_token,
    // Cognito does not return a new refresh token on refresh: keep the old one.
    refresh_token: json.refresh_token || previous?.refresh_token,
    expires_at: Date.now() + (json.expires_in || 3600) * 1000,
  };
}

/**
 * Send a signed-out user to log in. With no social provider switched on this goes straight to the
 * hosted UI exactly as before; otherwise it shows the chooser first. Resolves never.
 */
export async function startLogin(returnTo: string = location.pathname + location.search): Promise<never> {
  if (socialEnabled({ google: AUTH_GOOGLE, apple: AUTH_APPLE })) {
    try {
      localStorage.setItem(K.redirect, returnTo);
    } catch {}
    location.assign(SIGNIN_PATH);
    return new Promise<never>(() => {});
  }
  return beginAuthorize(returnTo);
}

/** Redirect to the hosted UI authorize endpoint, optionally straight to a provider. */
export async function beginAuthorize(returnTo?: string, provider?: Provider): Promise<never> {
  if (returnTo !== undefined) {
    try {
      localStorage.setItem(K.redirect, returnTo);
    } catch {}
  }
  const verifier = randomString(48);
  const state = randomString(16);
  localStorage.setItem(K.verifier, verifier);
  localStorage.setItem(K.state, state);
  if (provider) localStorage.setItem(K.provider, provider);
  else localStorage.removeItem(K.provider);
  location.assign(
    buildAuthorizeUrl({
      authDomain: AUTH_DOMAIN,
      clientId: COGNITO_CLIENT_ID,
      redirectUri: redirectUri(),
      state,
      challenge: await challengeFor(verifier),
      provider,
      locale: getLocale(),
    }),
  );
  return new Promise<never>(() => {});
}

/** Where the chooser sends the user after login (set by startLogin; same-origin paths only). */
export function pendingReturnPath(): string {
  try {
    return safeReturnPath(localStorage.getItem(K.redirect), "/generations/index.html");
  } catch {
    return "/generations/index.html";
  }
}

/**
 * Finish the login on /auth/callback. The `state` check is strict: BOTH values must be present
 * and equal (the previous inline script skipped the check when either was missing).
 * Returns where to send the user next.
 */
export async function completeLogin(): Promise<string> {
  const url = new URL(location.href);
  const code = url.searchParams.get("code");
  const incoming = url.searchParams.get("state");
  const stored = localStorage.getItem(K.state);
  const verifier = localStorage.getItem(K.verifier);
  const fallback = "/generations/index.html";
  const error = url.searchParams.get("error");
  const target = () => {
    const t = localStorage.getItem(K.redirect);
    localStorage.removeItem(K.redirect);
    // only same-origin relative paths: never an open redirect
    return safeReturnPath(t, fallback);
  };

  if (error) {
    const description = url.searchParams.get("error_description");
    // The state must match for errors too: an attacker must not be able to steer the retry.
    if (!stored || !incoming || stored !== incoming) throw new Error("Invalid login state");
    const provider = parseProvider(localStorage.getItem(K.provider));
    let retried = false;
    try {
      retried = sessionStorage.getItem(K.retry) === "1";
    } catch {}
    if (shouldRetry(description, retried)) {
      try {
        sessionStorage.setItem(K.retry, "1");
      } catch {
        throw new AuthDisplayError(sanitizeAuthError(error, description, getLocale()));
      }
      return beginAuthorize(undefined, provider);
    }
    localStorage.removeItem(K.verifier);
    localStorage.removeItem(K.state);
    throw new AuthDisplayError(sanitizeAuthError(error, description, getLocale()));
  }
  if (!code) return target();
  if (!stored || !incoming || stored !== incoming || !verifier) {
    throw new Error("Invalid login state");
  }
  const json = await tokenRequest({
    grant_type: "authorization_code",
    code,
    redirect_uri: redirectUri(),
    code_verifier: verifier,
  });
  writeTokens(toTokens(json));
  localStorage.removeItem(K.verifier);
  localStorage.removeItem(K.state);
  try {
    sessionStorage.removeItem(K.retry);
  } catch {}
  return target();
}

/** Back-compat for pages that land with ?code= (e.g. the generations page). */
export async function handleAuthCodeIfPresent(): Promise<void> {
  const next = await completeLogin();
  history.replaceState({}, "", next);
}

/** Valid tokens (refreshing if near expiry), or null when signed out. */
export async function getTokensIfAvailable(): Promise<Tokens | null> {
  const t = readTokens();
  if (!t) return null;
  if (t.expires_at - SKEW_MS > Date.now()) return t;
  if (!t.refresh_token) {
    signOut();
    return null;
  }
  try {
    const next = toTokens(await tokenRequest({ grant_type: "refresh_token", refresh_token: t.refresh_token }), t);
    writeTokens(next);
    return next;
  } catch {
    signOut();
    return null;
  }
}

export function userIdFromIdToken(idToken: string): string | null {
  try {
    const payload = JSON.parse(atob(idToken.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return payload.sub || payload["cognito:username"] || null;
  } catch {
    return null;
  }
}

/**
 * Authorization header + user id for API calls. When signed out this sends the user to log in
 * (and never resolves) so callers don't have to special-case it.
 */
export async function getAuthorizationHeader(): Promise<{ Authorization: string; userId: string | null }> {
  const t = await getTokensIfAvailable();
  if (!t) return startLogin();
  return { Authorization: `Bearer ${t.id_token}`, userId: userIdFromIdToken(t.id_token) };
}

/** Called on every protected page: bounce to login when there is no valid session. */
export async function bootstrapAuthForPage(): Promise<void> {
  if ((await getTokensIfAvailable()) === null) await startLogin();
}
