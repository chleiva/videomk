// Light / dark choice. "auto" follows the system (prefers-color-scheme in tokens.css); "light" and "dark" set html[data-theme].
export type ThemeChoice = "auto" | "light" | "dark";
export const THEME_KEY = "vmk_theme";

export function normalizeTheme(v: unknown): ThemeChoice {
  return v === "light" || v === "dark" ? v : "auto";
}

export function savedTheme(): ThemeChoice {
  try { return normalizeTheme(localStorage.getItem(THEME_KEY)); } catch { return "auto"; }
}

export function applyTheme(choice: ThemeChoice): void {
  const el = document.documentElement;
  if (choice === "auto") el.removeAttribute("data-theme"); else el.setAttribute("data-theme", choice);
}

export function setTheme(choice: ThemeChoice): void {
  try { if (choice === "auto") localStorage.removeItem(THEME_KEY); else localStorage.setItem(THEME_KEY, choice); } catch { /* private mode: lasts until reload */ }
  applyTheme(choice);
}
