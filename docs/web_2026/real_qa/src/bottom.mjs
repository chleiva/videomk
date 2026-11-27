import { open, BASE } from "./lib.mjs";
const { browser, page, shot } = await open({ w: 390, h: 844, theme: "light", lang: "en", tag: "_390_bottom" });
for (const [path, name, sel] of [["/watch?id=32cad559-20e1-506d-be7c-56f04fa43789", "watch", ".watch-chips a:last-child"], ["/settings", "settings", "main"], ["/generations", "videos", ".vtile:last-child"]]) {
  await page.goto(BASE + path); await page.waitForLoadState("networkidle").catch(() => {}); await page.waitForTimeout(1500);
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight)); await page.waitForTimeout(500); await shot("b_" + name);
  const r = await page.evaluate((sel) => { const el = [...document.querySelectorAll(sel)].pop(), bar = document.querySelector(".app-tabbar, .tabbar, nav[class*=tab]"); const a = el?.getBoundingClientRect(), b = bar?.getBoundingClientRect(); return { lastBottom: a && Math.round(a.bottom), barTop: b && Math.round(b.top), barClass: bar?.className }; }, sel);
  console.log(name, JSON.stringify(r));
}
await browser.close();
