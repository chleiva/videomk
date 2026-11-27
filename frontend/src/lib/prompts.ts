// "The prompt" beside a video (design bar, web Watch): the sentence that made it. The video API does not return it yet, so the browser that made the video remembers it
// (this device only, newest 60, wiped with the rest of the local data on sign-out of a deleted account: the key starts with vmk_). A server that sends `prompt` wins.
const KEY = "vmk_prompts";
const MAX = 60, MAX_LEN = 1500;
type Entry = [id: string, prompt: string];

function read(): Entry[] {
  try {
    const a = JSON.parse(localStorage.getItem(KEY) || "[]");
    return Array.isArray(a) ? a.filter((e): e is Entry => Array.isArray(e) && typeof e[0] === "string" && typeof e[1] === "string") : [];
  } catch { return []; }
}

/** Pure: the list after remembering one more (newest first, one entry per video, at most 60). Empty ids or prompts change nothing. */
export function withPrompt(list: Entry[], id: string, prompt: string): Entry[] {
  const text = prompt.trim().slice(0, MAX_LEN);
  if (!id || !text) return list;
  return [[id, text] as Entry, ...list.filter((e) => e[0] !== id)].slice(0, MAX);
}

export function rememberPrompt(id: string, prompt: string): void {
  try { localStorage.setItem(KEY, JSON.stringify(withPrompt(read(), id, prompt))); } catch { /* private mode or full: the page simply shows no prompt */ }
}

export function promptFor(id: string): string | null {
  return read().find((e) => e[0] === id)?.[1] ?? null;
}

/** What the page shows: the server's prompt when it sends one, else what this browser remembers, else nothing (never the title dressed up as a prompt). */
export function pickPrompt(fromServer: unknown, remembered: string | null): string | null {
  const s = typeof fromServer === "string" ? fromServer.trim() : "";
  return (s || remembered?.trim() || "").slice(0, MAX_LEN) || null;
}
