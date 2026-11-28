// The real network behind the ClipUploader: the separate video-uploads API (address from capabilities.video_upload.api_url, the same token as the main API), then the file straight to
// its presigned S3 slot. Never logs or shows a code or a raw error: the callers show the server's `message` or our own sentence.
import { getAuthorizationHeader } from "./auth";
import { isExpectedS3Url, uploadToSlot } from "./deck";
import { currentLocaleHeaders } from "./i18n";
import { clipUrl, parseClip, parseRefusal } from "./videoClips";
import type { AnalyseResult, Clip, ClipDeps, GetResult, SlotResult } from "./videoClips";

export async function sha256Hex(blob: Blob): Promise<string> {
  const buf = await blob.arrayBuffer();
  const d = new Uint8Array(await crypto.subtle.digest("SHA-256", buf));
  return Array.from(d, (b) => b.toString(16).padStart(2, "0")).join("");
}

async function json(res: Response): Promise<any> { try { return await res.json(); } catch { return {}; } }
const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

export function clipDeps(apiUrl: string): ClipDeps {
  const call = async (method: string, id?: string, action?: "analyse", body?: unknown) => {
    const { Authorization, userId } = await getAuthorizationHeader();
    if (!userId) throw new Error("auth");
    return fetch(clipUrl(apiUrl, userId, id, action), { method, headers: { Authorization, ...(body !== undefined ? { "Content-Type": "application/json" } : {}), ...currentLocaleHeaders() }, ...(body !== undefined ? { body: JSON.stringify(body) } : {}) });
  };
  return {
    sha256: sha256Hex, sleep, now: () => Date.now(),
    async createSlot(req): Promise<SlotResult> {
      let res: Response;
      try { res = await call("POST", undefined, undefined, req); } catch { return { kind: "refused", failure: { kind: "network", retry: true } }; }
      const b = await json(res);
      if (res.status === 200 && b?.duplicate === true) { const clip = parseClip(b); if (clip) return { kind: "duplicate", clip }; }
      if (res.status === 201 || res.status === 200) {
        const up = b?.upload;
        if (typeof b?.id === "string" && up && typeof up.url === "string" && up.fields && typeof up.fields === "object" && isExpectedS3Url(up.url)) return { kind: "slot", id: b.id, url: up.url, fields: up.fields };
        return { kind: "refused", failure: { kind: "error", retry: true } };
      }
      return { kind: "refused", failure: parseRefusal(res.status, b) };
    },
    post: (slot, blob, onProgress, signal) => uploadToSlot({ id: "", url: slot.url, fields: slot.fields }, blob, onProgress, signal).then((r) => (r.ok ? { ok: true as const } : { ok: false as const, code: r.code === "aborted" ? ("aborted" as const) : ("failed" as const) })),
    async analyse(id): Promise<AnalyseResult> {
      try {
        const res = await call("POST", id, "analyse", {});
        const b = await json(res);
        if (res.status === 200 || res.status === 202) return { ok: true, clip: parseClip(b) ?? undefined };
        return { ok: false, failure: parseRefusal(res.status, b) };
      } catch { return { ok: false, failure: { kind: "network", retry: true } }; }
    },
    async getClip(id): Promise<GetResult> {
      try {
        const res = await call("GET", id);
        if (res.status === 404) return { ok: false, notFound: true };
        if (!res.ok) return { ok: false };
        const clip = parseClip(await json(res));
        return clip ? { ok: true, clip } : { ok: false };
      } catch { return { ok: false }; }
    },
    async remove(id) { try { await call("DELETE", id); } catch { /* it expires by itself */ } },
  };
}

/** The last 14 days of clips (ready and in progress), newest first: the "Recent clips" list. A fresh signed thumbnail comes with every read, so nothing is cached. */
export async function listClips(apiUrl: string): Promise<Clip[] | null> {
  try {
    const { Authorization, userId } = await getAuthorizationHeader();
    if (!userId) return null;
    const res = await fetch(clipUrl(apiUrl, userId), { headers: { Authorization, ...currentLocaleHeaders() } });
    if (!res.ok) return null;
    const b = await res.json();
    return (Array.isArray(b?.clips) ? b.clips : []).map((c: unknown) => parseClip(c)).filter((c: Clip | null): c is Clip => !!c);
  } catch { return null; }
}
