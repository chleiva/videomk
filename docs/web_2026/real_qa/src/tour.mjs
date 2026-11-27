// node tour.mjs <w> <theme> <lang> [only]  : every signed-in page at one size, theme and language, against the real QA API
import { open, BASE } from "./lib.mjs";
const [w, theme, lang, only] = [Number(process.argv[2] || 1440), process.argv[3] || "light", process.argv[4] || "en", process.argv[5] || ""];
const tag = `_${w}_${theme}_${lang}`;
const { browser, page, log, shot } = await open({ w, h: w < 500 ? 844 : 900, theme, lang, tag });
const pages = [["/generations", "videos"], ["/new", "create"], ["/media", "media"], ["/settings", "settings"], ["/wallet", "wallet"]].filter(([, n]) => !only || only.split(",").includes(n));
for (const [path, name] of pages) {
  await page.goto(BASE + path); await page.waitForLoadState("networkidle").catch(() => {}); await page.waitForTimeout(1200);
  await shot("t_" + name);
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  if (over > 1) log.push(`overflow-x ${over}px on ${name}`);
}
if (!only || only.includes("watch")) {
  await page.goto(BASE + "/generations"); await page.waitForSelector(".vtile-link");
  const n = Number(process.env.NTH || 0);
  await page.locator(".vtile-link").nth(n).click(); await page.waitForURL(/watch/); await page.waitForSelector("video", { timeout: 20000 }); await page.waitForTimeout(2500);
  await shot("t_watch");
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  if (over > 1) log.push(`overflow-x ${over}px on watch`);
}
console.log(tag, log.length ? "\n" + [...new Set(log)].join("\n") : "clean");
await browser.close();
