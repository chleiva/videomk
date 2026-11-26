// Send feedback (docs/FEEDBACK.md): POST /users/{userId}/feedback. The request builder and the status mapping are pure (tested); `sendFeedback` is the fetch around them.
import { getAuthorizationHeader } from "./auth";
import { apiGateway } from "./config";
import { currentLocaleHeaders, getLocale } from "./i18n";
import type { Locale } from "./i18n";

export const TEXT_MIN = 3;
export const TEXT_MAX = 2000;
export const KINDS = ["idea", "problem", "other"] as const;
export type Kind = (typeof KINDS)[number];
export const CONTEXTS = ["settings", "after_video", "rating_prompt"] as const;

export interface FeedbackBody { text: string; kind?: Kind; app: "web"; locale?: Locale; context?: string }

/** Control characters out (a newline stays, the server keeps it), surrounding space trimmed. */
export function cleanText(raw: string): string {
  return String(raw ?? "").replace(/\r\n?/g, "\n").replace(/[\u0000-\u0008\u000b-\u001f\u007f-\u009f​-‏‪-‮⁦-⁩﻿]/g, "").trim();
}

export function textProblem(raw: string): "short" | "long" | null {
  const n = [...cleanText(raw)].length;
  return n < TEXT_MIN ? "short" : n > TEXT_MAX ? "long" : null;
}

/** The context we may send: only the known ones (it comes from a query string). */
export function contextFrom(search: string): string {
  const v = new URLSearchParams(search).get("from") ?? "";
  return (CONTEXTS as readonly string[]).includes(v) ? v : "settings";
}

/** The request body, or null when the text is not sendable. */
export function buildFeedbackRequest(input: { text: string; kind?: Kind | null; locale?: Locale; context?: string }): FeedbackBody | null {
  const text = cleanText(input.text);
  if (textProblem(text)) return null;
  const body: FeedbackBody = { text, app: "web" };
  if (input.kind && (KINDS as readonly string[]).includes(input.kind)) body.kind = input.kind;
  if (input.locale === "en" || input.locale === "es") body.locale = input.locale;
  if (input.context) body.context = input.context.slice(0, 64);
  return body;
}

export type FeedbackFailure = "invalid" | "rate" | "auth" | "error" | "network";
export type FeedbackResult = { ok: true } | { ok: false; failure: FeedbackFailure };

export function failureFor(status: number): FeedbackFailure {
  if (status === 400) return "invalid";
  if (status === 429) return "rate";
  if (status === 401 || status === 403) return "auth";
  return "error";
}

export async function sendFeedback(input: { text: string; kind?: Kind | null; context?: string }): Promise<FeedbackResult> {
  const body = buildFeedbackRequest({ ...input, locale: getLocale() });
  if (!body) return { ok: false, failure: "invalid" };
  const { Authorization, userId } = await getAuthorizationHeader();
  if (!userId) return { ok: false, failure: "auth" };
  try {
    const res = await fetch(apiGateway.feedback(userId), { method: "POST", headers: { "Content-Type": "application/json", Authorization, ...currentLocaleHeaders() }, body: JSON.stringify(body) });
    return res.ok ? { ok: true } : { ok: false, failure: failureFor(res.status) };
  } catch {
    return { ok: false, failure: "network" };
  }
}
