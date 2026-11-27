// Live checks of https://videomk.com and https://app.videomk.com (no sign-in, nothing typed): node live_check.mjs <outdir>
import { chromium } from "/Users/chleiva/code/incident-command-agent/node_modules/playwright-core/index.mjs";
import path from "path"; import fs from "fs";
const OUT = process.argv[2] || "live"; fs.mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch({ channel: "chrome" });
const out = [];
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: "dark" });
const page = await ctx.newPage();
const errs = []; page.on("pageerror", (e) => errs.push(String(e).slice(0, 120)));
// 1. home: hero video plays, posters, Create carries the prompt
await page.goto("https://videomk.com/", { waitUntil: "load" }); await page.waitForTimeout(3500);
const v = await page.evaluate(() => { const x = document.querySelector("video[data-sample=forest]"); return x ? { paused: x.paused, t: x.currentTime, muted: x.muted, ready: x.readyState } : null; });
out.push("hero video " + JSON.stringify(v));
out.push("posters " + JSON.stringify(await page.evaluate(() => [...document.querySelectorAll("video[data-sample]")].map((x) => x.getAttribute("poster")))));
await page.screenshot({ path: path.join(OUT, "01_home_live_dark_1440.jpg"), type: "jpeg", quality: 82 });
await page.evaluate(() => document.querySelector("#gallery").scrollIntoView()); await page.waitForTimeout(2500);
await page.screenshot({ path: path.join(OUT, "02_home_gallery_live_1440.jpg"), type: "jpeg", quality: 82 });
out.push("gallery first frames playing " + JSON.stringify(await page.evaluate(() => [...document.querySelectorAll(".mk-rail video")].map((x) => [x.dataset.sample, !x.paused, Number(x.currentTime.toFixed(1))]))));
await page.evaluate(() => scrollTo(0, 0));
await page.fill("#hero-prompt", "How is honey made, for curious kids");
await Promise.all([page.waitForURL(/app\.videomk\.com/, { timeout: 20000 }), page.click(".mk-ask-btn")]);
await page.waitForTimeout(3500);
out.push("after hero Create -> " + page.url().slice(0, 120));
out.push("stored return path " + (await page.evaluate(() => localStorage.getItem("vmk_auth_redirect") || Object.entries(localStorage).filter(([k]) => /redirect|return/i.test(k)).map(([k, v]) => k + "=" + v).join(" | ")).catch(() => "?")));
await page.screenshot({ path: path.join(OUT, "03_signin_live_1440.jpg"), type: "jpeg", quality: 82 });
// 2. sign-in: Continue with Google reaches Google (no account is picked)
const g = page.locator("button:has-text('Google'), a:has-text('Google')").first();
if (await g.count()) { await g.click(); await page.waitForURL(/accounts\.google\.com|login\.videomk\.com/, { timeout: 20000 }).catch(() => {}); await page.waitForTimeout(2500); const u = new URL(page.url()); out.push("Google click -> " + u.host + u.pathname.slice(0, 40) + " redirect_uri=" + (u.searchParams.get("redirect_uri") || "") + " client=" + (u.searchParams.get("client_id") || "").slice(0, 14)); }
else out.push("NO GOOGLE BUTTON");
// 3. routes
for (const p of ["/generations", "/new", "/media", "/watch?id=x", "/edit?id=x", "/wallet", "/settings", "/feedback", "/signin", "/auth/callback?error=access_denied"]) { const r = await ctx.request.get("https://app.videomk.com" + p); out.push(`app ${p} ${r.status()} ${(await r.text()).includes("videomk") ? "shell" : "?"}`); }
await page.goto("https://app.videomk.com/auth/callback?error=access_denied&error_description=cancelled", { waitUntil: "load" }); await page.waitForTimeout(2500);
out.push("callback error page text: " + (await page.locator("main").innerText()).replace(/\s+/g, " ").slice(0, 160));
await page.screenshot({ path: path.join(OUT, "04_callback_error_live.jpg"), type: "jpeg", quality: 80 });
for (const p of ["/", "/es/", "/privacy", "/terms", "/support", "/delete-account", "/samples/jobs.mp4", "/signin", "/generations"]) { const r = await ctx.request.get("https://videomk.com" + p, { maxRedirects: 0 }).catch((e) => ({ status: () => "ERR", headers: () => ({}) })); out.push(`site ${p} ${r.status()} ${r.headers()["location"] || ""}`); }
// 4. light + phone + Spanish
for (const [n, w, h, scheme, url] of [["05_home_live_light_1440", 1440, 900, "light", "https://videomk.com/"], ["06_home_live_phone_390", 390, 844, "dark", "https://videomk.com/"], ["07_home_live_es_1440", 1440, 900, "dark", "https://videomk.com/es/"], ["08_signin_live_phone_390", 390, 844, "dark", "https://app.videomk.com/signin"]]) {
  const c = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme, deviceScaleFactor: w < 500 ? 2 : 1 }); const p = await c.newPage(); await p.goto(url, { waitUntil: "load" }); await p.waitForTimeout(3000); await p.screenshot({ path: path.join(OUT, n + ".jpg"), type: "jpeg", quality: 82 }); await c.close();
}
out.push("page errors: " + JSON.stringify(errs));
await browser.close(); console.log(out.join("\n"));
