import { getAuthorizationHeader } from "./auth";
import { apiGateway } from "./config";

export type StartResult =
  | { ok: true; videoId: string }
  | { ok: false; kind: "invalid" | "quota" | "auth" | "error"; message: string };

/** Start a generation. Returns a typed result so the UI can say what actually went wrong. */
export async function startGeneration(prompt: string, clientRequestId: string): Promise<StartResult> {
  const { Authorization, userId } = await getAuthorizationHeader();
  if (!userId) return { ok: false, kind: "auth", message: "You must be signed in to create a video." };
  let res: Response;
  try {
    res = await fetch(apiGateway.generateVideo(userId), {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization },
      body: JSON.stringify({ prompt, client_request_id: clientRequestId }),
    });
  } catch {
    return { ok: false, kind: "error", message: "Network problem. Please try again." };
  }
  let body: any = {};
  try {
    body = await res.json();
  } catch {}
  if (res.ok) return { ok: true, videoId: String(body.video_id || "") };
  if (res.status === 400) return { ok: false, kind: "invalid", message: body.message || "That prompt can't be used." };
  if (res.status === 429)
    return { ok: false, kind: "quota", message: body.message || "You've reached today's limit. Try again tomorrow." };
  if (res.status === 401 || res.status === 403)
    return { ok: false, kind: "auth", message: "Your session expired. Please sign in again." };
  return { ok: false, kind: "error", message: "We couldn't start your video. Please try again." };
}

export function newRequestId(): string {
  return (globalThis.crypto?.randomUUID?.() as string) || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
