// Screenshots of the home page: node shoot_home.mjs <outdir> [base]   (base default http://127.0.0.1:4321; pass https://videomk.com for the live site)
import { chromium } from "/Users/chleiva/code/incident-command-agent/node_modules/playwright-core/index.mjs";
import path from "path"; import fs from "fs";
const OUT = process.argv[2] || "shots", BASE = process.argv[3] || "http://127.0.0.1:4321";
fs.mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch({ channel: "chrome" });
for (const [name, w, h, scheme, url, clipH] of [["home_dark", 1440, 900, "dark", "/", 1880], ["home_light", 1440, 900, "light", "/", 1880], ["home_es_dark", 1440, 900, "dark", "/es/", 1000], ["home_phone_dark", 390, 844, "dark", "/", 1700], ["home_phone_light", 390, 844, "light", "/", 844], ["home_820", 820, 1000, "dark", "/", 1400]]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  await page.goto(BASE + url, { waitUntil: "load", timeout: 30000 });
  await page.waitForTimeout(2500);
  await page.screenshot({ path: path.join(OUT, name + ".jpg"), type: "jpeg", quality: 80, clip: { x: 0, y: 0, width: w, height: clipH }, fullPage: true });
  await ctx.close();
}
await browser.close(); console.log("done");
