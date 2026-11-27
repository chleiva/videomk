import { describe, expect, it } from "vitest";
import { buildAuthorizeUrl, chooserOptions, isLinkRaceError, parseProvider, safeReturnPath, sanitizeAuthError, shouldRetry, socialEnabled } from "./authUrl";

const base = { authDomain: "https://auth.example.com", clientId: "cid", redirectUri: "https://x.test/auth/callback", state: "st4te", challenge: "chal" };
const params = (u: string) => new URL(u).searchParams;

describe("locale in the authorize URL and the chooser", () => {
  it("English adds nothing; Spanish adds lang=es", () => {
    expect(params(buildAuthorizeUrl({ ...base, locale: "en" })).has("lang")).toBe(false);
    expect(buildAuthorizeUrl({ ...base, locale: "en" })).toBe(buildAuthorizeUrl(base));
    expect(params(buildAuthorizeUrl({ ...base, locale: "es" })).get("lang")).toBe("es");
  });
  it("speaks the person's language in labels and errors", () => {
    expect(chooserOptions({ google: true, apple: true }, "es").map((o) => o.label)).toEqual(["Continuar con Google", "Continuar con Apple", "Continuar con correo"]);
    expect(chooserOptions({ google: true, apple: false }).map((o) => o.label)).toEqual(["Continue with Google", "Continue with email"]);
    expect(sanitizeAuthError("access_denied", null, "es")).toBe("Se canceló el inicio de sesión.");
    expect(sanitizeAuthError("server_error", "boom", "es")).toBe("No se pudo iniciar sesión: boom");
    expect(sanitizeAuthError("x", null, "es")).toBe("No se pudo iniciar sesión. Inténtalo de nuevo.");
  });
});

describe("buildAuthorizeUrl", () => {
  it("is unchanged when no provider (email path)", () => {
    const u = buildAuthorizeUrl(base);
    expect(u.startsWith("https://auth.example.com/oauth2/authorize?")).toBe(true);
    const p = params(u);
    expect(p.has("identity_provider")).toBe(false);
    expect(Object.fromEntries(p)).toEqual({
      response_type: "code", client_id: "cid", redirect_uri: base.redirectUri, scope: "openid email profile",
      state: "st4te", code_challenge_method: "S256", code_challenge: "chal",
    });
  });
  it("adds the case-sensitive provider and keeps state and PKCE", () => {
    for (const prov of ["Google", "SignInWithApple"] as const) {
      const p = params(buildAuthorizeUrl({ ...base, provider: prov }));
      expect(p.get("identity_provider")).toBe(prov);
      expect(p.get("state")).toBe("st4te");
      expect(p.get("code_challenge_method")).toBe("S256");
      expect(p.get("code_challenge")).toBe("chal");
      expect(p.get("response_type")).toBe("code");
    }
  });
  it("parseProvider only accepts the two exact values", () => {
    expect(parseProvider("Google")).toBe("Google");
    expect(parseProvider("SignInWithApple")).toBe("SignInWithApple");
    expect(parseProvider("google")).toBeUndefined();
    expect(parseProvider("evil")).toBeUndefined();
    expect(parseProvider(null)).toBeUndefined();
  });
});

describe("retry-once guard", () => {
  const d = "Already found an entry for username Google_123";
  it("detects the quirk", () => {
    expect(isLinkRaceError(d)).toBe(true);
    expect(isLinkRaceError("something else")).toBe(false);
    expect(isLinkRaceError(null)).toBe(false);
  });
  it("retries only the first time", () => {
    expect(shouldRetry(d, false)).toBe(true);
    expect(shouldRetry(d, true)).toBe(false);
    expect(shouldRetry("other", false)).toBe(false);
  });
});

describe("sanitizeAuthError", () => {
  it("strips markup and control characters and truncates", () => {
    const m = sanitizeAuthError("server_error", "<img src=x onerror=alert(1)>\u0000 boom " + "a".repeat(500));
    expect(m).not.toMatch(/[<>=]/);
    expect(m.length).toBeLessThan(200);
  });
  it("friendly messages", () => {
    expect(sanitizeAuthError("access_denied", "user cancelled")).toBe("Sign-in was cancelled.");
    expect(sanitizeAuthError(null, "Already found an entry for username x")).toContain("try signing in again");
    expect(sanitizeAuthError("x", "")).toBe("Sign-in failed. Please try again.");
  });
});

describe("render logic", () => {
  it("both off: only email, and chooser not used", () => {
    expect(socialEnabled({ google: false, apple: false })).toBe(false);
    expect(chooserOptions({ google: false, apple: false }).map((o) => o.id)).toEqual(["email"]);
  });
  it("renders a button only when its switch is on", () => {
    expect(chooserOptions({ google: true, apple: false }).map((o) => o.id)).toEqual(["google", "email"]);
    expect(chooserOptions({ google: false, apple: true }).map((o) => o.id)).toEqual(["apple", "email"]);
    const all = chooserOptions({ google: true, apple: true });
    expect(all.map((o) => o.label)).toEqual(["Continue with Google", "Continue with Apple", "Continue with email"]);
  });
});

describe("safeReturnPath", () => {
  it("blocks open redirects", () => {
    expect(safeReturnPath("//evil.com", "/f")).toBe("/f");
    expect(safeReturnPath("https://evil.com", "/f")).toBe("/f");
    expect(safeReturnPath("/\\evil.com", "/f")).toBe("/f");
    expect(safeReturnPath("/a?b=1", "/f")).toBe("/a?b=1");
    expect(safeReturnPath(null, "/f")).toBe("/f");
  });
});
