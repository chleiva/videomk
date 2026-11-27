import { chromium } from "playwright-core";
const S = process.env.OUT || "/tmp/videomk-web-qa"; const BASE = process.env.BASE || "http://127.0.0.1:4400";
const b = await chromium.launch({ channel: "chrome" });
for (const [w, theme, lang] of [[1440, "dark", "en"], [1440, "light", "es"], [390, "light", "en"], [390, "dark", "es"]]) {
  const ctx = await b.newContext({ viewport: { width: w, height: w < 500 ? 844 : 900 }, colorScheme: theme, deviceScaleFactor: w < 500 ? 2 : 1 });
  const p = await ctx.newPage(); const errs = []; p.on("console", (m) => m.type() === "error" && errs.push(m.text().slice(0, 150))); p.on("pageerror", (e) => errs.push(String(e).slice(0, 150)));
  const reqs = []; p.on("request", (r) => /samples\//.test(r.url()) && reqs.push(r.url().split("/").pop()));
  await p.goto(BASE + (lang === "es" ? "/es/" : "/")); await p.waitForLoadState("load"); await p.waitForTimeout(1500);
  const early = [...reqs];
  await p.screenshot({ path: `${S}/shots/h_top_${w}_${theme}_${lang}.png` });
  await p.locator("#gallery").scrollIntoViewIfNeeded(); await p.evaluate(() => window.scrollBy(0, 250)); await p.waitForTimeout(2500);
  await p.screenshot({ path: `${S}/shots/h_gallery_${w}_${theme}_${lang}.png` });
  const posters = await p.evaluate(() => [...document.querySelectorAll("video[data-sample]")].map((v) => `${v.dataset.sample}:${v.getAttribute("poster") ? "poster" : "none"}`));
  const over = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  console.log(w, theme, lang, "| before scroll:", early.join(","), "| posters after scroll:", posters.join(" "), "| h1:", JSON.stringify(await p.locator("h1").innerText()), "| overflow", over, "| errors", errs.length ? errs : "none");
  await ctx.close();
}
await b.close();
