// Screenshots of the built marketing site (videomk.com) at 1440 / 820 / 390, light and dark, EN and ES. Usage:
//   python3 -m http.server 4398 --directory <built site>  &   node shoot_marketing.mjs <outdir>
// PW_CORE can point at any playwright-core install (the repo has none of its own); uses the installed Chrome.
import fs from "fs";
const core = process.env.PW_CORE || "/Users/chleiva/code/incident-command-agent/node_modules/playwright-core/index.mjs";
const { chromium } = await import(core);
const OUT = process.argv[2] || "shots";
const BASE = process.env.BASE || "http://localhost:4398";
fs.mkdirSync(OUT, { recursive: true });
const SIZES = { d1440: [1440, 900], t820: [820, 1100], p390: [390, 844] };
const PAGES = { home: "/", home_es: "/es/", privacy: "/privacy/", support: "/support/" };
const only = process.env.ONLY ? process.env.ONLY.split(",") : null;
const browser = await chromium.launch({ channel: "chrome" });
for (const [sz, [w, h]] of Object.entries(SIZES)) {
  for (const scheme of ["light", "dark"]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme, reducedMotion: process.env.MOTION === "1" ? "no-preference" : "reduce", deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    for (const [name, path] of Object.entries(PAGES)) {
      if (only && !only.includes(name)) continue;
      await page.goto(BASE + path, { waitUntil: "load" });
      await page.waitForTimeout(400);
      await page.screenshot({ path: `${OUT}/${name}__${sz}__${scheme}.png`, fullPage: true });
      if (name.startsWith("home")) await page.screenshot({ path: `${OUT}/${name}__${sz}__${scheme}__fold.png` });
    }
    await ctx.close();
  }
}
await browser.close();
console.log("done");
