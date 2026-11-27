// Behaviour checks of package B in a real browser against a mocked API: node verify_b.mjs   (needs the built app on BASE and playwright-core + Chrome)
import { chromium } from "/Users/chleiva/code/incident-command-agent/node_modules/playwright-core/index.mjs";
import fs from "fs";
const BASE = process.env.BASE || "http://127.0.0.1:4399";
const IMG = "/private/tmp/claude-501/-Users-chleiva-code-videomk/1c20d537-4a97-40b0-81a8-700c1738b8ff/scratchpad/catalog/final/objects";
const origs = fs.readdirSync(`${IMG}/p`).filter((f) => f.endsWith(".jpg")).slice(0, 4).map((f) => `${IMG}/p/${f}`);
const b64 = (o) => Buffer.from(JSON.stringify(o)).toString("base64url");
const tokens = { access_token: "a", id_token: `${b64({ alg: "none" })}.${b64({ sub: "user-1" })}.x`, refresh_token: "r", expires_at: Date.now() + 5 * 3600e3 };
const caps = { aspects: [{ id: "16:9", label: "Landscape", ready: true }], resolutions: [{ id: "1080p", label: "1080p", credits_multiplier: 1, aspects: ["16:9"] }, { id: "2160p", label: "4K", credits_multiplier: 2, aspects: ["16:9"] }], platforms: [{ id: "youtube", label: "YouTube", aspect: "16:9", resolution: "1080p", recommended_minutes: 5, max_minutes: null, supports_4k: true }, { id: "other", label: "Just a video", aspect: "16:9", resolution: "1080p", recommended_minutes: 1, max_minutes: null, supports_4k: true }], languages: [], lengths: { min_minutes: 0.25, max_minutes: 12, presets: [0.5, 1, 2, 5] }, intake: false };
const results = [];
const ok = (name, cond, extra = "") => results.push(`${cond ? "PASS" : "FAIL"} ${name} ${extra}`);
const browser = await chromium.launch({ channel: "chrome" });
async function ctxFor(handlers = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  await ctx.addInitScript((t) => { localStorage.setItem("vmk_auth_tokens", JSON.stringify(t)); localStorage.setItem("vmk_media_privacy_seen", "1"); localStorage.removeItem("vmk_create_defaults"); }, tokens);
  const gen = []; let n = 0;
  await ctx.route(/media\.s3|assets\.s3/, (r) => r.request().method() === "OPTIONS" ? r.fulfill({ status: 204, headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "*" } }) : r.fulfill({ status: 204, headers: { "access-control-allow-origin": "*" } }));
  await ctx.route(/thumbs\.test/, (r) => r.fulfill({ status: 200, contentType: "image/jpeg", body: fs.readFileSync(origs[0]), headers: { "access-control-allow-origin": "*" } }));
  await ctx.route(/backend\.videomk\.com/, async (route) => {
    const req = route.request(), u = req.url();
    const json = (o, s = 200) => route.fulfill({ status: s, contentType: "application/json", headers: { "access-control-allow-origin": "*" }, body: JSON.stringify(o) });
    if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*" } });
    if (u.includes("/capabilities")) return json(caps);
    if (u.includes("/wallet")) return json({ balance: 50, unlimited: false, buckets: [] });
    if (u.endsWith("/videos/generate")) { gen.push(JSON.parse(req.postData() || "{}")); return json({ video_id: "v-new" }); }
    if (/\/videos$/.test(u)) return json({ items: [] });
    if (/\/uploads$/.test(u)) return json({ uploads: [{ id: `d${++n}`, url: "https://assets.s3.amazonaws.com/", fields: { key: `uploads/user-1/d${n}.jpg` } }] });
    if (u.includes("/library/summary")) return json({ plan: "free", limit_bytes: 2e9, used_bytes: 1, read_only: false, count: 3, years: [], places: [], collections: [], prefs: { organize: "ask" } });
    if (u.includes("/library/items")) return json({ items: [0, 1, 2].map((i) => ({ id: `ph${i}`, added: "2026-03-01T10:00:00Z", w: 1, h: 1, bytes: 1, thumb_url: "https://thumbs.test/x.jpg", collections: [] })) });
    return json({}, 404);
  });
  return { ctx, gen };
}
// 1. plain create: body, redirect, toast
try {
  const { ctx, gen } = await ctxFor(); const page = await ctx.newPage();
  await page.goto(`${BASE}/new/`, { waitUntil: "networkidle" });
  await page.fill("#create-text", "How a forest breathes, for curious teenagers");
  await page.click(".compose-go");
  await page.waitForURL(/generations\/?\?started=1|generations\/?$/, { timeout: 8000 });
  ok("create posts platform/aspect/resolution/length", gen[0]?.platform === "other" && gen[0]?.aspect === "16:9" && gen[0]?.resolution === "1080p" && gen[0]?.target_minutes === 1, JSON.stringify(gen[0]));
  ok("create sends a client_request_id", typeof gen[0]?.client_request_id === "string" && gen[0].client_request_id.length > 8);
  await page.waitForSelector(".toast", { timeout: 5000 }).then(() => ok("videos shows the started toast", true), () => ok("videos shows the started toast", false));
  ok("the started flag is cleaned from the address", !page.url().includes("started"));
  await ctx.close();
} catch (e) { results.push("FAIL block threw: " + String(e).slice(0, 200)); }
// 2. YouTube + 4K + look
try {
  const { ctx, gen } = await ctxFor(); const page = await ctx.newPage();
  await page.goto(`${BASE}/new/`, { waitUntil: "networkidle" });
  await page.fill("#create-text", "A history of the printing press in depth");
  await page.click("button[aria-label='Made for']"); await page.click("[role=menuitemradio]:has-text('YouTube')");
  await page.click("button[aria-label='Look']"); await page.click("[role=menuitemradio]:has-text('Paper')");
  await page.click("button[aria-label='Options']"); await page.click("[role=radio]:has-text('4K')"); await page.click("text=Done");
  const cta = await page.textContent(".compose-go");
  ok("price shows 5 min x 2 = 10 credits", /10/.test(cta ?? ""), cta ?? "");
  await page.click(".compose-go"); await page.waitForURL(/generations/, { timeout: 8000 });
  ok("body: youtube, 2160p, theme paper, 5 min", gen[0]?.platform === "youtube" && gen[0]?.resolution === "2160p" && gen[0]?.theme === "paper" && gen[0]?.target_minutes === 5, JSON.stringify(gen[0]));
  await ctx.close();
} catch (e) { results.push("FAIL block threw: " + String(e).slice(0, 200)); }
// 3. photos from this device are uploaded first, then sent as media ids
try {
  const { ctx, gen } = await ctxFor(); const page = await ctx.newPage();
  await page.goto(`${BASE}/new/`, { waitUntil: "networkidle" });
  await page.fill("#create-text", "My weekend away, warm and relaxed");
  await page.setInputFiles("input[type=file][accept='image/*']", origs.slice(0, 3).map((p, i) => ({ name: `a${i}.jpg`, mimeType: "image/jpeg", buffer: fs.readFileSync(p) })));
  await page.waitForFunction(() => !document.querySelector(".compose-go")?.textContent?.includes("Adding"), null, { timeout: 15000 });
  await page.click(".compose-go"); await page.waitForURL(/generations/, { timeout: 8000 });
  ok("three uploaded photos go as media ids", Array.isArray(gen[0]?.media) && gen[0].media.length === 3 && gen[0].media.every((x) => /^d\d+$/.test(x)), JSON.stringify(gen[0]?.media));
  await ctx.close();
} catch (e) { results.push("FAIL block threw: " + String(e).slice(0, 200)); }
// 4. My media -> Make a video hands the photos to the composer (library_media)
try {
  const { ctx, gen } = await ctxFor(); const page = await ctx.newPage();
  await page.goto(`${BASE}/media/`, { waitUntil: "networkidle" });
  await page.click(".mtile:nth-child(1) .mtile-check"); await page.click(".mtile:nth-child(2) .mtile-check");
  await page.click("text=Make a video"); await page.waitForURL(/\/new/, { timeout: 8000 });
  await page.waitForSelector(".attach", { timeout: 5000 });
  ok("the composer shows the 2 chosen photos", (await page.locator(".attach").count()) === 2);
  await page.fill("#create-text", "My holiday in Thailand 2026, calm and warm");
  await page.click(".compose-go"); await page.waitForURL(/generations/, { timeout: 8000 });
  ok("body carries library_media ids", JSON.stringify(gen[0]?.library_media) === JSON.stringify(["ph0", "ph1"]), JSON.stringify(gen[0]?.library_media));
  await ctx.close();
} catch (e) { results.push("FAIL block threw: " + String(e).slice(0, 200)); }
// 5. keyboard shortcuts
try {
  const { ctx } = await ctxFor(); const page = await ctx.newPage();
  await page.goto(`${BASE}/generations/`, { waitUntil: "networkidle" });
  await page.keyboard.press("?"); ok("? opens the shortcuts sheet", await page.locator("[role=dialog] kbd").count() > 0);
  await page.keyboard.press("Escape");
  await page.keyboard.press("g"); await page.keyboard.press("m"); await page.waitForURL(/\/media/, { timeout: 5000 }); ok("G then M goes to Media", true); await page.waitForSelector("input[type=search]"); await page.waitForTimeout(400);
  await page.keyboard.press("/"); ok("/ focuses the media search", await page.evaluate(() => document.activeElement?.getAttribute("type") === "search"));
  await page.keyboard.press("Escape"); await page.evaluate(() => document.activeElement?.blur());
  await page.keyboard.press("n"); await page.waitForURL(/\/new/, { timeout: 5000 }); ok("N goes to Create", true);
  await ctx.close();
} catch (e) { results.push("FAIL block threw: " + String(e).slice(0, 200)); }
// 6. old create link
try {
  const { ctx } = await ctxFor(); const page = await ctx.newPage();
  await page.goto(`${BASE}/generations/?new=1&prompt=hello%20bees%20world`, { waitUntil: "networkidle" });
  await page.waitForURL(/\/new\/?\?prompt=/, { timeout: 5000 }).then(() => ok("generations?new=1&prompt= redirects to /new with the prompt", true), () => ok("old create link redirect", false, page.url()));
  await page.waitForSelector("#create-text");
  ok("the prompt is prefilled", (await page.inputValue("#create-text")) === "hello bees world");
  await ctx.close();
} catch (e) { results.push("FAIL block threw: " + String(e).slice(0, 200)); }
await browser.close();
console.log(results.join("\n"));
