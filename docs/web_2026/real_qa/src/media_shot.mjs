import { open, BASE } from "./lib.mjs";
for (const [w, theme, lang] of [[1440, "light", "en"], [390, "dark", "es"]]) {
  const { browser, page, log, shot } = await open({ w, h: w < 500 ? 844 : 900, theme, lang, tag: `_${w}_${theme}_${lang}` });
  await page.goto(BASE + "/media"); await page.waitForSelector(".mtile img"); await page.waitForTimeout(800);
  await page.locator(".page-tools .btn-quiet").click(); for (let i = 0; i < 3; i++) await page.locator(".mtile-btn").nth(i).click();
  await page.waitForTimeout(500); await shot("t_media_selected");
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  await page.locator(".selbar-go").click(); await page.waitForURL(/\/new/); await page.waitForSelector(".attach-strip"); await page.waitForTimeout(1200); await shot("t_create_photos");
  console.log(w, theme, lang, "overflow", over, log.join(" ; ") || "clean"); await browser.close();
}
