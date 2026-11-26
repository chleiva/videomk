// The footer light / dark / auto switch. Hidden in the markup; shown only when this script runs (the public static pages carry no scripts and follow the system).
import { savedTheme, setTheme } from "./theme";
import type { ThemeChoice } from "./theme";

export function initThemeSwitch(): void {
  const row = document.querySelector<HTMLElement>("[data-theme-switch]");
  if (!row) return;
  row.hidden = false;
  const draw = () => row.querySelectorAll<HTMLButtonElement>("[data-theme-option]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.themeOption === savedTheme())));
  row.querySelectorAll<HTMLButtonElement>("[data-theme-option]").forEach((b) => b.addEventListener("click", () => { setTheme(b.dataset.themeOption as ThemeChoice); draw(); }));
  draw();
}
