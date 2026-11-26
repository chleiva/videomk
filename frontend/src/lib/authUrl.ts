// Pure helpers for the sign-in flow (no DOM access, so they are unit-tested directly).

/** Cognito identity_provider values. Case-sensitive. */
export type Provider = "Google" | "SignInWithApple";
export const COGNITO_PROVIDER: Record<"google" | "apple", Provider> = {
  google: "Google",
  apple: "SignInWithApple",
};

export interface Switches {
  google: boolean;
  apple: boolean;
}

/** The chooser is only used when at least one social provider is switched on. */
export const socialEnabled = (s: Switches): boolean => s.google || s.apple;

export interface AuthorizeInput {
  authDomain: string;
  clientId: string;
  redirectUri: string;
  state: string;
  challenge: string;
  provider?: Provider;
}

export function buildAuthorizeUrl(i: AuthorizeInput): string {
  const q = new URLSearchParams({
    response_type: "code",
    client_id: i.clientId,
    redirect_uri: i.redirectUri,
    scope: "openid email profile",
    state: i.state,
    code_challenge_method: "S256",
    code_challenge: i.challenge,
  });
  if (i.provider) q.set("identity_provider", i.provider);
  return `${i.authDomain}/oauth2/authorize?${q.toString()}`;
}

/** Only these values may come back from storage; anything else means "no provider". */
export function parseProvider(v: string | null | undefined): Provider | undefined {
  return v === "Google" || v === "SignInWithApple" ? v : undefined;
}

/** Cognito quirk: first federated sign-in after an account link can fail with this text. */
export const isLinkRaceError = (description: string | null | undefined): boolean =>
  !!description && description.includes("Already found an entry for username");

/** Retry exactly once per attempt chain: `alreadyRetried` is the session flag. */
export const shouldRetry = (description: string | null | undefined, alreadyRetried: boolean): boolean =>
  isLinkRaceError(description) && !alreadyRetried;

/**
 * Text that is safe and useful to show for a callback error. Never echoes provider-supplied text
 * beyond a stripped, truncated snippet, and callers must render it with textContent.
 */
export function sanitizeAuthError(error: string | null | undefined, description: string | null | undefined): string {
  if (error === "access_denied" && !isLinkRaceError(description)) return "Sign-in was cancelled.";
  if (isLinkRaceError(description)) return "We could not finish linking your accounts. Please try signing in again.";
  const clean = (description || "")
    .replace(/[^\p{L}\p{N} .,'’:;()\-_/]/gu, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 160);
  return clean ? `Sign-in failed: ${clean}` : "Sign-in failed. Please try again.";
}

/** Same-origin relative paths only (never an open redirect). */
export const safeReturnPath = (t: string | null | undefined, fallback: string): string =>
  t && t.startsWith("/") && !t.startsWith("//") && !t.startsWith("/\\") ? t : fallback;

export interface ChooserOption {
  id: "google" | "apple" | "email";
  label: string;
}

/** What the chooser renders: switched-on providers first, email always. */
export function chooserOptions(s: Switches): ChooserOption[] {
  const out: ChooserOption[] = [];
  if (s.google) out.push({ id: "google", label: "Continue with Google" });
  if (s.apple) out.push({ id: "apple", label: "Continue with Apple" });
  out.push({ id: "email", label: "Continue with email" });
  return out;
}
