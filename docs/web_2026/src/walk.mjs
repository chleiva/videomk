import { chromium } from "/Users/chleiva/code/incident-command-agent/node_modules/playwright-core/index.mjs";
import fs from "fs";
import path from "path";
const OUT = process.argv[2] || "shots", ONLY = process.argv[3] || "";
const BASE = process.env.BASE || "http://127.0.0.1:4321";
const IMG = process.env.IMGDIR || "/private/tmp/claude-501/-Users-chleiva-code-videomk/1c20d537-4a97-40b0-81a8-700c1738b8ff/scratchpad/catalog/final/objects";
const thumbs = fs.readdirSync(path.join(IMG, "t")).filter((f) => f.endsWith(".jpg")).slice(0, 40);
const origs = fs.readdirSync(path.join(IMG, "p")).filter((f) => f.endsWith(".jpg")).slice(0, 14).map((f) => path.join(IMG, "p", f));
fs.mkdirSync(OUT, { recursive: true });
const SIZES = { d1440: [1440, 900], t820: [820, 1000], p390: [390, 844] };
const b64 = (o) => Buffer.from(JSON.stringify(o)).toString("base64url");
const tokens = { access_token: "a", id_token: `${b64({ alg: "none" })}.${b64({ sub: "user-1" })}.x`, refresh_token: "r", expires_at: Date.now() + 5 * 3600e3 };
const now = Date.now(), iso = (h) => new Date(now - h * 3600e3).toISOString();
const T = (i) => `https://thumbs.test/${i % thumbs.length}.jpg`;
const caps = (extra = {}) => ({
  aspects: [{ id: "16:9", label: "Landscape", ready: true }, { id: "9:16", label: "Vertical", ready: true }, { id: "1:1", label: "Square", ready: true }, { id: "4:5", label: "Portrait", ready: true }],
  resolutions: [{ id: "720p", label: "720p", credits_multiplier: 1, aspects: ["16:9", "9:16", "1:1", "4:5"] }, { id: "1080p", label: "1080p", credits_multiplier: 1, aspects: ["16:9", "9:16", "1:1", "4:5"] }, { id: "2160p", label: "4K", credits_multiplier: 2, aspects: ["16:9"] }],
  platforms: [{ id: "youtube", label: "YouTube", aspect: "16:9", resolution: "1080p", recommended_minutes: 5, max_minutes: null, supports_4k: true }, { id: "tiktok", label: "TikTok", aspect: "9:16", resolution: "1080p", recommended_minutes: 0.5, max_minutes: 3, supports_4k: false, note_4k: "TikTok shows 1080p." }, { id: "linkedin", label: "LinkedIn", aspect: "4:5", resolution: "1080p", recommended_minutes: 1, max_minutes: 10, supports_4k: false }, { id: "other", label: "Just a video", aspect: "16:9", resolution: "1080p", recommended_minutes: 1, max_minutes: null, supports_4k: true }],
  languages: [{ id: "en", label: "English" }, { id: "es", label: "Español" }],
  lengths: { min_minutes: 0.25, max_minutes: 12, presets: [0.25, 0.5, 0.75, 1, 2, 3, 5, 8, 12] }, max_photos: 100, intake: true, deck: { max_mb: 50, max_slides: 60, formats: ["pptx", "pdf"] },
  watermark: { modes: [{ id: "none", label: "None", available: true }, { id: "videomk", label: "videomk", available: true }, { id: "custom", label: "Your logo", available: false, requires: "premium" }], forced: false, premium: false }, ...extra,
});
const videos = [
  { video_id: "v1", title: "How a forest breathes", status: "RENDERING", created_at: iso(0.1), eta_seconds: 150 },
  { video_id: "v2", title: "Why the sky is blue", status: "COMPLETE", created_at: iso(2), duration_s: 91, editable: true, preview_gif_url: T(2), video_url: "/x.mp4" },
  { video_id: "v3", title: "The history of the printing press", status: "COMPLETE", created_at: iso(5), duration_s: 182, editable: true, preview_gif_url: T(5) },
  { video_id: "v4", title: "Compound interest in 60 seconds", status: "ERROR", created_at: iso(30) },
  { video_id: "v5", title: "What is photosynthesis", status: "COMPLETE", created_at: iso(52), duration_s: 60, editable: true, preview_gif_url: T(9) },
  { video_id: "v6", title: "Mortgage rates explained for first-time buyers in the UK", status: "COMPLETE", created_at: iso(90), duration_s: 312, editable: true, preview_gif_url: T(13) },
  { video_id: "v7", title: "A lighthouse keeper's story", status: "COMPLETE", created_at: iso(120), duration_s: 130, preview_gif_url: T(17) },
  { video_id: "v8", title: "How bees make honey", status: "COMPLETE", created_at: iso(150), duration_s: 75, preview_gif_url: T(21) },
];
const photo = (i) => ({ id: `ph${i}`, taken: `2026-0${1 + (i % 6)}-${10 + (i % 17)}T10:00:00`, added: iso(i), place: i % 4 === 0 ? "Phuket, Thailand" : undefined, w: 1600, h: 1200, bytes: 1.4e6, thumb_url: T(i), collections: [] });
const photos = Array.from({ length: 48 }, (_, i) => photo(i));
const summary = (o = {}) => ({ plan: "free", limit_bytes: 2e9, used_bytes: 1.2e9, read_only: false, count: 48, can_upgrade: false, years: [{ year: 2026, count: 40 }, { year: 2025, count: 8 }], places: [{ name: "Phuket, Thailand", country: "Thailand", count: 12 }, { name: "Paris, France", country: "France", count: 9 }], collections: [{ id: "c1", name: "Family", emoji: "🏡", count: 14 }, { id: "c2", name: "Phuket · 14–21 Jul 2026", count: 12, auto: true }], prefs: { organize: "ask" }, ...o });
// ---- walkthrough (docs/web_2026/src/walk.mjs): the owner's tour of the web app against a MOCKED API (http://127.0.0.1:8787), built on shoot_b's data.
// node walk.mjs <outdir>   (dev server: PUBLIC_API_BASE=http://127.0.0.1:8787 astro dev --port 4321)
const POSTERS = ["forest", "bees", "pulpo", "jobs", "agents", "focus"].map((n) => `${BASE}/samples/${n}.webp`);
const vids = [
  { video_id: "v1", title: "How a forest breathes", status: "RENDERING", created_at: iso(0.1), eta_seconds: 150 },
  { video_id: "f1", title: "Mattia tells us about his little brother", status: "FAILED", can_retry: true, created_at: iso(0.4) },
  { video_id: "v2", title: "How bees turn nectar into honey", status: "COMPLETE", created_at: iso(2), duration_s: 91, editable: true, preview_gif_url: POSTERS[1], video_url: "/samples/bees.mp4" },
  { video_id: "v3", title: "How a forest breathes and why forests matter", status: "COMPLETE", created_at: iso(5), duration_s: 91, editable: true, preview_gif_url: POSTERS[0] },
  { video_id: "v5", title: "El pulpo: ocho brazos y mucho cerebro", status: "COMPLETE", created_at: iso(52), duration_s: 15, editable: true, preview_gif_url: POSTERS[2] },
  { video_id: "v6", title: "Your job in 10 years", status: "COMPLETE", created_at: iso(90), duration_s: 60, editable: true, preview_gif_url: T(13) },
  { video_id: "v7", title: "A lighthouse keeper's story", status: "COMPLETE", created_at: iso(120), duration_s: 130, preview_gif_url: T(17) },
];
const walletV = { balance: 9, unlimited: false, buckets: [{ kind: "daily", remaining: 1, expires_at: Math.floor(now / 1000) + 3600 * 5 }, { kind: "signup", remaining: 8, expires_at: null }], next_daily_at: Math.floor(now / 1000) + 3600 * 20, history: [] };
async function setup(ctx, s) {
  let list = vids.map((v) => ({ ...v }));
  await ctx.route(/thumbs\.test/, (r) => { const n = Number(r.request().url().split("/").pop().replace(".jpg", "")); r.fulfill({ status: 200, contentType: "image/jpeg", body: fs.readFileSync(path.join(IMG, "t", thumbs[n % thumbs.length])) }); });
  await ctx.route(/127\.0\.0\.1:8787/, async (route) => {
    const req = route.request(), u = req.url().split("?")[0], m = req.method();
    const json = (o, st = 200) => route.fulfill({ status: st, contentType: "application/json", headers: { "access-control-allow-origin": "*" }, body: JSON.stringify(o) });
    if (m === "OPTIONS") return route.fulfill({ status: 204, headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*" } });
    if (u.includes("/capabilities")) return json(caps());
    if (u.includes("/wallet")) return json(walletV);
    if (u.includes("/watermark")) return m === "GET" ? json({ watermark: { mode: "videomk", position: "auto", has_logo: false }, capabilities: { modes: [{ id: "none", available: true }, { id: "videomk", available: true }, { id: "custom", available: false, requires: "premium" }], forced: false, premium: false, logo: { max_bytes: 2097152, types: ["image/png"] } } }) : json({});
    if (u.endsWith("/videos/brief")) { await new Promise((x) => setTimeout(x, s.slowBrief ? 60000 : 200)); return json({ status: "ok" }); }
    if (u.endsWith("/videos/generate")) return json({ video_id: "new1" });
    if (u.endsWith("/retry") && m === "POST") { s.calls?.push("retry " + u.split("/").slice(-2)[0]); const id = u.split("/").slice(-2)[0]; if (s.retry409) return json({ code: "attachments_unavailable", message: "Some photos of this video are no longer available.", photos: 45, missing: 3 }, 409); list = list.map((v) => (v.video_id === id ? { ...v, status: "STARTED_PROCESSING", can_retry: undefined } : v)); return json({ message: "workflow restarted", video_id: id, status: "STARTED_PROCESSING", retries: 1, photos: 45 }, 202); }
    const vm = u.match(/\/videos\/([a-z]\d)$/);
    if (vm && m === "DELETE") { s.calls?.push("delete " + vm[1]); list = list.filter((v) => v.video_id !== vm[1]); return json({ message: "deleted", video_id: vm[1] }); }
    if (vm) return json({ video_id: vm[1], status: "COMPLETE", title: "How a forest breathes and why forests matter", description: "A calm explainer about how a forest breathes.\n\nVideo: AI-generated video (videomk library).", url: "/samples/forest.mp4" });
    if (/\/videos$/.test(u) && m === "POST") { s.calls?.push("POST videos"); return json({}, 500); }
    if (/\/videos$/.test(u)) return json({ items: list });
    if (u.includes("/library/summary")) return json(summary());
    if (u.includes("/library/search")) return json({ understood: { chips: [] }, items: photos.filter((p) => p.place), mode: "timeline" });
    if (u.includes("/library/items")) return json({ items: photos });
    if (u.includes("/library/collections")) return json({ collections: summary().collections });
    return json({}, 404);
  });
}
const SZ = { d: [1440, 900], p: [390, 844] };
const out = [];
const browser = await chromium.launch({ channel: "chrome" });
async function shot(name, sz, url, { scheme = "dark", locale = "en", s = {}, act } = {}) {
  const [w, h] = SZ[sz];
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme, locale: locale === "es" ? "es-ES" : "en-US", deviceScaleFactor: sz === "p" ? 2 : 1 });
  tokens.id_token = `${b64({ alg: "none" })}.${b64({ sub: "user-1", email: "chris@example.com" })}.x`;
  await ctx.addInitScript(([t, loc]) => { try { localStorage.setItem("vmk_auth_tokens", JSON.stringify(t)); localStorage.setItem("vmk_locale", loc); localStorage.setItem("vmk_media_privacy_seen", "1"); } catch {} }, [tokens, locale]);
  await setup(ctx, s);
  const page = await ctx.newPage();
  const errs = [];
  page.on("pageerror", (e) => errs.push(String(e).slice(0, 160)));
  let note = "ok";
  try {
    await page.goto(BASE + url, { waitUntil: "networkidle", timeout: 30000 });
    await page.waitForTimeout(900);
    if (act) note = (await act(page, s)) || "ok";
    await page.screenshot({ path: path.join(OUT, `${name}_${sz === "d" ? 1440 : 390}.jpg`), type: "jpeg", quality: 82 });
  } catch (e) { note = "FAILED " + String(e).slice(0, 220); }
  out.push(`${name}_${sz} ${note}${errs.length ? " ERR " + errs.join(" | ") : ""}`);
  await ctx.close();
}
const PROMPT = "How a forest breathes, for curious teenagers";
for (const sz of ["d", "p"]) {
  await shot("04_videos", sz, "/generations/");
  await shot("05a_create_empty", sz, "/new/");
  await shot("05_create", sz, "/new/?prompt=" + encodeURIComponent(PROMPT), { act: async (p) => { const v = await p.locator("#create-text").inputValue(); return v === PROMPT ? "prompt carried" : "PROMPT NOT CARRIED: " + v; } });
  await shot("06_create_locked", sz, "/new/?prompt=" + encodeURIComponent(PROMPT), { s: { slowBrief: true }, act: async (p) => { await p.locator(".compose-go").click(); await p.waitForTimeout(700); const inert = await p.locator("form.composer-card").evaluate((f) => f.hasAttribute("inert")); const txt = await p.locator(".compose-progress").innerText(); return `inert=${inert} status="${txt.replace(/\n/g, " ")}"`; } });
  await shot("07_media_selected", sz, "/media/", { act: async (p) => { await p.locator("button:has-text('Select')").first().click(); for (const n of [1, 2, 4, 7, 9]) await p.locator(".mtile-btn").nth(n).click(); await p.waitForTimeout(300); return "bar=" + (await p.locator(".selbar-go").innerText()); } });
}
await shot("08_watch", "d", "/watch/?id=v3");
await shot("09_settings", "d", "/settings/");
await shot("10_credits", "d", "/wallet/");
await shot("04b_videos_light", "d", "/generations/", { scheme: "light" });
await shot("05b_create_es", "p", "/new/", { locale: "es" });
// ---- behaviour checks (no screenshots kept for these beyond the first)
const calls = [];
await shot("11_retry_in_place", "d", "/generations/", { s: { calls }, act: async (p) => { const before = await p.locator(".vtile, .making-card, [class*=making]").count(); await p.locator(".vtile.is-failed button:has-text('Try again')").click(); await p.waitForTimeout(1500); const failed = await p.locator(".vtile.is-failed").count(); const tiles = await p.locator(".vgrid > *").count(); return `calls=${JSON.stringify(calls)} failedCardsAfter=${failed} gridItems=${tiles}`; } });
const calls2 = [];
await shot("12_retry_409", "d", "/generations/", { s: { calls: calls2, retry409: true }, act: async (p) => { await p.locator(".vtile.is-failed button:has-text('Try again')").click(); await p.waitForTimeout(900); const failed = await p.locator(".vtile.is-failed").count(); const toast = await p.locator("[role=status]").allInnerTexts(); return `calls=${JSON.stringify(calls2)} failedCardsAfter=${failed} toast=${JSON.stringify(toast.filter(Boolean).slice(-1))}`; } });
const calls3 = [];
await shot("13_remove", "d", "/generations/", { s: { calls: calls3 }, act: async (p) => { await p.locator(".vtile.is-failed button:has-text('Remove')").click(); await p.waitForTimeout(900); return `calls=${JSON.stringify(calls3)} failedCardsAfter=${await p.locator(".vtile.is-failed").count()}`; } });
await shot("14_media_back_keeps_selection", "d", "/media/", { act: async (p) => { await p.locator("button:has-text('Select')").first().click(); for (const n of [1, 2, 4]) await p.locator(`.mtile:nth-child(${n}) .mtile-btn`).first().click(); await p.locator(".selbar-go").click(); await p.waitForURL(/\/new/); await p.waitForTimeout(1200); const attached = await p.locator(".attach").count(); await p.goBack(); await p.waitForTimeout(1500); const bar = await p.locator(".selbar-go").innerText().catch(() => "NO BAR"); return `attachedInCreate=${attached} afterBack="${bar}"`; } });
await browser.close();
console.log(out.join("\n"));
