// Keyboard shortcuts of the app (docs/WEB_REDESIGN_2026.md 6.3): N new video, / search, G then V / M / C go to Videos / Media / Credits, ? the shortcut sheet.
// Pure state machine over key events (tested in shortcuts.test.ts); the component wires it to the document. Never fires while someone is typing or holding a modifier.
export type Dest = "videos" | "media" | "credits" | "new";
export interface ShortcutHandlers { go(dest: Dest): void; search(): boolean | void; help(): void }
export interface KeyLike { key: string; ctrlKey?: boolean; metaKey?: boolean; altKey?: boolean; target?: { tagName?: string; isContentEditable?: boolean; getAttribute?: (n: string) => string | null } | null }

export const G_WINDOW_MS = 1500;
const TYPING = new Set(["INPUT", "TEXTAREA", "SELECT"]);

export function isTyping(t: KeyLike["target"]): boolean {
  if (!t) return false;
  return TYPING.has((t.tagName ?? "").toUpperCase()) || t.isContentEditable === true || t.getAttribute?.("role") === "textbox";
}

export function createShortcuts(h: ShortcutHandlers, now: () => number = Date.now) {
  let gAt = 0;
  /** Returns true when the key was a shortcut (the caller then prevents the browser's default). */
  return function onKey(e: KeyLike): boolean {
    if (e.ctrlKey || e.metaKey || e.altKey || isTyping(e.target)) return false;
    const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
    const waitingForG = gAt > 0 && now() - gAt <= G_WINDOW_MS;
    gAt = 0;
    if (waitingForG) {
      const d = ({ v: "videos", m: "media", c: "credits" } as const)[k as "v" | "m" | "c"];
      if (d) { h.go(d); return true; }
    }
    if (k === "g") { gAt = now(); return true; }
    if (k === "n") { h.go("new"); return true; }
    if (k === "/") return h.search() !== false;
    if (k === "?") { h.help(); return true; }
    return false;
  };
}

/** The sheet's rows: keys and the i18n key of what they do. */
export const SHORTCUT_ROWS: { keys: string[]; key: string }[] = [
  { keys: ["N"], key: "gen.sc_new" }, { keys: ["/"], key: "gen.sc_search" }, { keys: ["G", "V"], key: "gen.sc_videos" },
  { keys: ["G", "M"], key: "gen.sc_media" }, { keys: ["G", "C"], key: "gen.sc_credits" }, { keys: ["?"], key: "gen.sc_help" },
];
