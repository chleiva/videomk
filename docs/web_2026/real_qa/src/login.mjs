import { chromium } from "playwright-core";
import fs from "fs"; import os from "os";
const S = process.env.S; const email = process.argv[2];
const pw = fs.readFileSync(os.homedir() + "/.videomk-secrets/qa-tester6.pw", "utf8").trim();
const b = await chromium.launch({ channel: "chrome" });
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
const p = await ctx.newPage();
p.on("console", (m) => { if (m.type() === "error") console.log("console.error:", m.text().slice(0, 200)); });
await p.goto("http://localhost:4321/generations");
await p.waitForURL(/amazoncognito|signin/, { timeout: 20000 });
console.log("at", p.url().split("?")[0]);
if (/\/signin/.test(p.url())) { await p.screenshot({ path: S + "/shots/signin_1440.png" }); await p.getByRole("button", { name: /email/i }).click(); await p.waitForURL(/amazoncognito/); }
await p.waitForLoadState("networkidle");
await p.screenshot({ path: S + "/shots/hosted_login.png" });
const user = p.locator('input[name="username"]:visible').first();
await user.fill(email);
if (!(await p.locator('input[name="password"]:visible').count())) { await p.locator('button[type="submit"]:visible').first().click(); await p.locator('input[name="password"]:visible').first().waitFor(); }
await p.locator('input[name="password"]:visible').first().fill(pw);
await p.locator('button[type="submit"]:visible, input[type="submit"]:visible').first().click();
try { await p.waitForURL(/localhost:4321\/(generations|new|media)/, { timeout: 25000 }); } catch (e) { console.log("did not return; at", p.url().split("?")[0]); await p.screenshot({ path: S + "/shots/hosted_login_fail.png" }); await b.close(); process.exit(1); }
await p.waitForTimeout(3000);
console.log("signed in, at", p.url());
await ctx.storageState({ path: S + "/pw/state.json" });
await p.screenshot({ path: S + "/shots/after_login.png" });
await b.close();
