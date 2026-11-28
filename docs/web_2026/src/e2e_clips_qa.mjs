// ONE real end-to-end of video clips against QA, in a real browser, through the real web code: pick -> sheet -> hash -> POST /video-uploads -> S3 -> analyse -> poll -> ready.
// Only two things are faked: capabilities.video_upload is patched on (QA's main stack is not redeployed with -c videoUpload=1 yet), and POST .../videos/generate is captured, not sent (no render cost).
// usage: node e2e_clips_qa.mjs <idtoken-file> <clip.mp4> <vidup-api-url> <outdir>      (the app built with PUBLIC_API_BASE=<QA main api> served on localhost:4321)
import { chromium } from "/Users/chleiva/code/incident-command-agent/node_modules/playwright-core/index.mjs";
import fs from "fs";
const [tokFile, clip, vapi, out] = process.argv.slice(2);
fs.mkdirSync(out, { recursive: true });
const tok = fs.readFileSync(tokFile, "utf8").trim();
const tokens = { access_token: tok, id_token: tok, refresh_token: "", expires_at: Date.now() + 50 * 60e3 };
const browser = await chromium.launch({ channel: "chrome" });
const ctx = await browser.newContext({ viewport: { width: 1280, height: 860 }, colorScheme: "light", locale: "en-US" });
await ctx.addInitScript((t) => { localStorage.setItem("vmk_auth_tokens", JSON.stringify(t)); localStorage.setItem("vmk_media_privacy_seen", "1"); }, tokens);
const wire = [];
await ctx.route(/\/capabilities$/, async (route) => {
  const res = await route.fetch(); const b = await res.json();
  b.video_upload = { ...b.video_upload, enabled: true, available: true, paused: false, clips_left_today: 20, api_url: vapi };
  await route.fulfill({ response: res, json: b });
});
await ctx.route(/\/videos\/generate$/, (route) => { wire.push({ GENERATE: JSON.parse(route.request().postData() || "{}") }); route.fulfill({ status: 200, contentType: "application/json", headers: { "access-control-allow-origin": "*" }, body: JSON.stringify({ video_id: "captured" }) }); });
await ctx.route(/\/videos\/brief$/, (route) => route.fulfill({ status: 200, contentType: "application/json", headers: { "access-control-allow-origin": "*" }, body: JSON.stringify({ status: "ok" }) }));
ctx.on("request", (r) => { const u = r.url(); if (u.includes("/video-uploads") || u.includes(".s3.")) wire.push({ [r.method()]: u.replace(/\?.*/, "").replace(/users\/[^/]+/, "users/<id>"), body: (r.postData() || "").slice(0, 160).replace(/[^\x20-\x7e]/g, ".") }); });
ctx.on("response", (r) => { const u = r.url(); if (u.includes("/video-uploads") || u.includes(".s3.")) wire.push({ status: r.status(), for: r.request().method() + " " + u.replace(/\?.*/, "").replace(/users\/[^/]+/, "users/<id>"), cors: r.headers()["access-control-allow-origin"] }); });
const page = await ctx.newPage();
page.on("requestfailed", (r) => wire.push({ FAILED: r.method() + " " + r.url().replace(/\?.*/, "").slice(0, 90), why: r.failure()?.errorText }));
page.on("console", (m) => { if (m.type() === "error") wire.push({ console: m.text().slice(0, 200) }); });
const errs = []; page.on("pageerror", (e) => errs.push(String(e).slice(0, 200)));
await page.goto("http://localhost:4321/new/", { waitUntil: "networkidle" });
await page.waitForTimeout(1000);
await page.locator("input[type=file][accept*='video/mp4']").first().setInputFiles(clip);
await page.waitForSelector(".clip-sheet"); await page.waitForTimeout(800);
await page.screenshot({ path: `${out}/e2e_1_sheet.png` });
await page.locator("label.clip-choice").first().click();
await page.locator(".clip-actions .btn-primary").click();
await page.waitForTimeout(800); await page.screenshot({ path: `${out}/e2e_2_uploading_or_checking.png` });
try { await page.waitForSelector(".attach.clip.is-ready", { timeout: 120000 }); } catch (e) { await page.screenshot({ path: `${out}/e2e_FAIL.png` }); console.log(JSON.stringify(wire, null, 1), errs); await browser.close(); process.exit(1); }
await page.waitForTimeout(500);
await page.fill("#create-text", "A short clip of my test pattern, with a calm voice"); await page.waitForTimeout(300);
await page.screenshot({ path: `${out}/e2e_3_ready.png` });
await page.locator(".compose-go").click(); await page.waitForTimeout(2500);
const keep = wire.filter((w) => JSON.stringify(w).match(/video-uploads|vidup|GENERATE|FAILED|console/)); console.log(JSON.stringify(keep.map((w) => JSON.stringify(w)), null, 1)); console.log("pageerrors", errs);
await browser.close();
