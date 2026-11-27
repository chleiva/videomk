import { chromium } from "../node_modules/playwright-core/index.mjs";
import fs from "fs";
const dir = process.argv[2], out = process.argv[3];
fs.mkdirSync(out, { recursive: true });
const b = await chromium.launch({ channel: "chrome", args: ["--allow-file-access-from-files"] });
for (const f of fs.readdirSync(dir).filter((x) => x.endsWith(".html"))) {
  const phone = f.includes("__phone__");
  const ctx = await b.newContext({ viewport: phone ? { width: 390, height: 844 } : { width: 1440, height: 900 }, deviceScaleFactor: phone ? 2 : 1 });
  const p = await ctx.newPage();
  await p.goto("file://" + process.cwd() + "/" + dir + "/" + f);
  await p.waitForTimeout(400);
  const full = f.startsWith("home") ;
  await p.screenshot({ path: out + "/" + f.replace(".html", ".png"), fullPage: full });
  await ctx.close();
}
await b.close();
