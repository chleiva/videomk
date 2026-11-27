// The real network behind the UploadQueue: two destinations. "library" puts photos in My media (slots from /library/uploads, with sha256 and the optional capture time and
// position); "direct" is the Create composer's own photos for one video (slots from /uploads, as the apps do), whose ids go in the generate request as `media`.
import { getAuthorizationHeader } from "./auth";
import { API_BASE } from "./config";
import { isExpectedS3Url, uploadToSlot } from "./deck";
import { currentLocaleHeaders } from "./i18n";
import { prepareImage } from "./imageprep";
import { requestLibrarySlots } from "./library";
import type { PostResult, QueueDeps, SlotAnswer } from "./upload";

const post: QueueDeps["post"] = async (slot, blob, onProgress, signal): Promise<PostResult> => {
  if (!isExpectedS3Url(slot.url)) return { ok: false, code: "failed" };
  const r = await uploadToSlot({ id: "", url: slot.url, fields: slot.fields }, blob, onProgress, signal);
  return r.ok ? { ok: true } : { ok: false, code: r.code === "aborted" ? "aborted" : "failed" };
};
const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

export function libraryDeps(): QueueDeps {
  return {
    prepare: prepareImage, post, sleep,
    async requestSlot(p): Promise<SlotAnswer> {
      const r = await requestLibrarySlots([{ size: p.blob.size, sha256: p.sha256, ...p.meta }]);
      if (!r.ok) return { ok: false, kind: r.kind, retryAfter: r.retryAfter };
      const s = r.slots[0];
      return s ? { ok: true, slot: { status: s.status, id: s.id, url: s.url, fields: s.fields, duplicate_of: s.duplicate_of } } : { ok: false, kind: "error" };
    },
  };
}

export function directDeps(): QueueDeps {
  return {
    prepare: prepareImage, post, sleep,
    async requestSlot(): Promise<SlotAnswer> {
      try {
        const { Authorization, userId } = await getAuthorizationHeader();
        if (!userId) return { ok: false, kind: "error" };
        const res = await fetch(`${API_BASE}/users/${encodeURIComponent(userId)}/uploads`, { method: "POST", headers: { Authorization, "Content-Type": "application/json", ...currentLocaleHeaders() }, body: JSON.stringify({ count: 1 }) });
        if (res.status === 429) return { ok: false, kind: "rate", retryAfter: Number(res.headers.get("Retry-After")) || undefined };
        if (!res.ok) return { ok: false, kind: "error" };
        const b = await res.json();
        const u = Array.isArray(b?.uploads) ? b.uploads[0] : null;
        if (!u || typeof u.id !== "string" || typeof u.url !== "string") return { ok: false, kind: "error" };
        return { ok: true, slot: { status: "upload", id: u.id, url: u.url, fields: u.fields } };
      } catch { return { ok: false, kind: "error" }; }
    },
  };
}
