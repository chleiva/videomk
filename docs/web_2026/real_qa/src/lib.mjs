import { chromium } from "playwright-core";
export const S = process.env.OUT || "/tmp/videomk-web-qa";
export const BASE = process.env.BASE || "http://localhost:4321";
export async function open({ w = 1440, h = 900, theme = "light", lang = "en", tag = "" } = {}) {
  const browser = await chromium.launch({ channel: "chrome" });
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, storageState: S + "/pw/state.json", colorScheme: theme, locale: lang === "es" ? "es-ES" : "en-GB", deviceScaleFactor: w < 500 ? 2 : 1, permissions: ["clipboard-read", "clipboard-write"] });
  await ctx.addInitScript(([theme, lang]) => { try { localStorage.setItem("vmk_theme", theme); localStorage.setItem("vmk_locale", lang); localStorage.setItem("vmk_lang", lang); } catch {} }, [theme, lang]);
  await ctx.addInitScript(() => { const add = () => { const st = document.createElement('style'); st.textContent = 'astro-dev-toolbar{display:none!important}'; document.documentElement.appendChild(st); }; if (document.documentElement) add(); else document.addEventListener('DOMContentLoaded', add); });
  const page = await ctx.newPage();
  const log = [];
  page.on("console", (m) => { if (m.type() === "error" && !/vitest|astro-dev-toolbar|\[vite\]/.test(m.text())) log.push("console: " + m.text().slice(0, 240)); });
  page.on("pageerror", (e) => log.push("pageerror: " + String(e).slice(0, 240)));
  page.on("requestfailed", (r) => { if (!/\.mp4|_astro|@vite|node_modules/.test(r.url())) log.push("reqfailed: " + r.method() + " " + r.url().split("?")[0].slice(0, 140) + " " + (r.failure()?.errorText || "")); });
  page.on("response", (r) => { const u = r.url(); if (r.status() >= 400 && /execute-api|amazonaws|amazoncognito/.test(u)) log.push("http " + r.status() + " " + r.request().method() + " " + u.split("?")[0].replace(/users\/[^/]+/, "users/U").slice(0, 140)); });
  const shot = async (name, full = false) => { await page.addStyleTag({ content: "astro-dev-toolbar{display:none!important}" }).catch(() => {}); await page.screenshot({ path: `${S}/shots/${name}${tag}.png`, fullPage: full }); };
  return { browser, ctx, page, log, shot };
}
