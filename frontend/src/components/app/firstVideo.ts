// "Has this account finished a video yet?" for Create: the example chips and the first-video price caption are for people who have not (docs/design_bar/CREATE_SCREEN_REDESIGN_BRIEF.md).
// The list the Videos page keeps in the session cache answers at once; otherwise ONE read of the list. true / false, or null when it cannot be told (then nothing teaching is shown).
import { getAuthorizationHeader } from "../../lib/auth";
import { apiGateway } from "../../lib/config";
import { currentLocaleHeaders } from "../../lib/i18n";
import { normalizeItem } from "../../lib/videos";

export function anyFinished(items: unknown): boolean {
  return Array.isArray(items) && items.some((i) => normalizeItem(i)?.status === "complete");
}

export async function hasFinishedVideo(): Promise<boolean | null> {
  try {
    const c = JSON.parse(sessionStorage.getItem("vmk_tasks") || "null");
    if (Array.isArray(c) && c.some((i: { status?: string }) => i?.status === "complete")) return true;
  } catch { /* no cache */ }
  try {
    const { Authorization, userId } = await getAuthorizationHeader();
    if (!userId) return null;
    const res = await fetch(apiGateway.listVideos(userId), { headers: { Authorization, ...currentLocaleHeaders() } });
    if (!res.ok) return null;
    const data = (await res.json()) as { items?: unknown[] };
    return anyFinished(data.items);
  } catch { return null; }
}
