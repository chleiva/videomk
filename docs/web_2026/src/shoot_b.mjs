// Screenshots of package B (Videos, Create, My media) against a MOCKED API: node shoot_b.mjs <outdir> [only-substring]
// Needs the built app served on BASE (astro preview, default http://127.0.0.1:4399) and playwright-core with Chrome. Nothing here talks to AWS.
import { chromium } from "/Users/chleiva/code/incident-command-agent/node_modules/playwright-core/index.mjs";
import fs from "fs";
import path from "path";
const OUT = process.argv[2] || "shots", ONLY = process.argv[3] || "";
const BASE = process.env.BASE || "http://127.0.0.1:4399";
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

async function setup(ctx, s) {
  let uploadN = 0;
  await ctx.route(/thumbs\.test/, (r) => { const n = Number(r.request().url().split("/").pop().replace(".jpg", "")); r.fulfill({ status: 200, contentType: "image/jpeg", body: fs.readFileSync(path.join(IMG, "t", thumbs[n % thumbs.length])), headers: { "access-control-allow-origin": "*" } }); });
  await ctx.route(/media\.s3\.amazonaws\.com|vmk-assets\.s3\.amazonaws\.com/, async (r) => { if (r.request().method() === "OPTIONS") return r.fulfill({ status: 204, headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "*" } }); await new Promise((x) => setTimeout(x, s.slowUpload ? 1500 : 60)); r.fulfill({ status: 204, headers: { "access-control-allow-origin": "*" } }); });
  await ctx.route(/backend\.videomk\.com/, async (route) => {
    const req = route.request(), u = req.url(), m = req.method();
    const json = (o, st = 200) => route.fulfill({ status: st, contentType: "application/json", headers: { "access-control-allow-origin": "*" }, body: JSON.stringify(o) });
    if (m === "OPTIONS") return route.fulfill({ status: 204, headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*" } });
    if (s.delay) await new Promise((x) => setTimeout(x, s.delay));
    if (u.includes("/capabilities")) return json(caps(s.caps));
    if (u.includes("/wallet")) return json({ balance: s.balance ?? 12, unlimited: false, buckets: [], next_daily_at: null });
    if (u.includes("/videos/brief")) return json(s.brief ?? { status: "ok" });
    if (u.endsWith("/videos/generate")) return json(s.generate ?? { video_id: "new1" });
    if (/\/videos$/.test(u) && m === "GET") return s.videosError ? json({ message: "x" }, 500) : json({ items: s.videos === "empty" ? [] : videos });
    if (u.includes("/library/summary")) return json(s.libEmpty ? summary({ count: 0, used_bytes: 0, years: [], places: [], collections: [] }) : summary(s.summary));
    if (u.includes("/library/search")) return json({ understood: { chips: [{ kind: "place", label: "Thailand" }, { kind: "date", label: "2026" }] }, items: photos.filter((p) => p.place), mode: "timeline" });
    if (u.includes("/library/uploads")) { const b = JSON.parse(req.postData() || "{}"); return json({ uploads: b.items.map((it, index) => ({ index, status: "upload", id: `n${++uploadN}`, url: "https://media.s3.amazonaws.com/", fields: { key: `o/user-1/n${uploadN}.jpg` } })), used_bytes: 1, limit_bytes: 2e9 }); }
    if (/\/library\/items\/ph\d+$/.test(u)) return json({ ...photos[0], url: T(3) });
    if (u.includes("/library/items")) return json({ items: s.libEmpty ? [] : photos });
    if (u.includes("/library/organize/preview")) return json({ total: 40, organized: 0, skipped: 3, groups: [{ name: "Phuket · 14–21 Jul 2026", count: 22 }, { name: "Paris · Mar 2026", count: 15 }] });
    if (u.includes("/library/collections")) return json({ collections: summary().collections });
    if (/\/uploads$/.test(u)) return json({ uploads: [{ id: "d" + ++uploadN, url: "https://vmk-assets.s3.amazonaws.com/", fields: { key: "uploads/user-1/x.jpg" } }] });
    return json({}, 404);
  });
}
const J = (name, p, combos, extra = {}) => ({ name, path: p, combos, ...extra });
const ALL = [["d1440", "light", "en"], ["d1440", "dark", "en"], ["p390", "light", "en"], ["p390", "dark", "en"]];
const jobs = [
  J("videos", "/generations/", ALL),
  J("videos_es", "/generations/", [["d1440", "light", "es"], ["p390", "light", "es"]]),
  J("videos_empty", "/generations/", [["d1440", "light", "en"], ["p390", "dark", "en"]], { s: { videos: "empty" } }),
  J("videos_error", "/generations/", [["d1440", "light", "en"]], { s: { videosError: true }, clearCache: true }),
  J("videos_loading", "/generations/", [["d1440", "light", "en"]], { s: { delay: 6000 }, wait: 700, clearCache: true, noIdle: true }),
  J("videos_search", "/generations/", [["d1440", "light", "en"]], { actions: [{ click: ".search-pill" }, { type: [".search-pill input", "photo"] }, { wait: 300 }] }),
  J("videos_menu", "/generations/", [["d1440", "light", "en"]], { actions: [{ hover: ".vtile:nth-child(2)" }, { click: ".vtile:nth-child(2) .vtile-more" }, { wait: 200 }] }),
  J("create_empty", "/new/", ALL),
  J("create_es", "/new/", [["d1440", "light", "es"], ["p390", "light", "es"]]),
  J("create_filled", "/new/", [["d1440", "light", "en"], ["p390", "dark", "en"]], { actions: [{ fill: ["#create-text", "How a forest breathes, for curious teenagers"] }, { wait: 200 }] }),
  J("create_length_menu", "/new/", [["d1440", "light", "en"]], { actions: [{ fill: ["#create-text", "How a forest breathes, for curious teenagers"] }, { click: "button[aria-label='Length']" }, { wait: 200 }] }),
  J("create_for_menu", "/new/", [["d1440", "dark", "en"]], { actions: [{ click: "button[aria-label='Made for']" }, { wait: 200 }] }),
  J("create_options", "/new/", [["d1440", "light", "en"], ["d1440", "dark", "en"], ["p390", "light", "en"]], { s: {}, actions: [{ fill: ["#create-text", "How a forest breathes, for curious teenagers"] }, { click: "button[aria-label='Options']" }, { wait: 300 }] }),
  J("create_photos", "/new/", [["d1440", "light", "en"], ["p390", "light", "en"]], { actions: [{ fill: ["#create-text", "My weekend in Phuket, relaxed and warm"] }, { files: ["input[type=file][accept='image/*']", "ORIG6"] }, { wait: 2500 }] }),
  J("create_questions", "/new/", [["d1440", "light", "en"], ["p390", "light", "en"]], { s: { brief: { status: "questions", questions: [{ id: "q1", text: "Who is this for?", options: [{ id: "a", label: "Kids" }, { id: "b", label: "Teenagers" }, { id: "c", label: "Adults" }], allow_other: false }] } }, actions: [{ fill: ["#create-text", "How a forest breathes, for curious teenagers"] }, { click: ".compose-go" }, { wait: 800 }] }),
  J("create_blocked", "/new/", [["d1440", "light", "en"]], { s: { brief: { status: "not_supported", message: "We can't make news about live events.", suggestion: "Try a general explainer instead." } }, actions: [{ fill: ["#create-text", "Breaking news about something happening now"] }, { click: ".compose-go" }, { wait: 800 }] }),
  J("create_nocredits", "/new/", [["d1440", "light", "en"]], { s: { balance: 1 }, actions: [{ fill: ["#create-text", "The history of the printing press in depth"] }, { click: "button[aria-label='Length']" }, { click: "text=5 min" }, { click: ".compose-go" }, { wait: 500 }] }),
  J("media", "/media/", ALL),
  J("media_es", "/media/", [["d1440", "light", "es"], ["p390", "light", "es"]]),
  J("media_empty", "/media/", [["d1440", "light", "en"], ["p390", "dark", "en"]], { s: { libEmpty: true } }),
  J("media_search", "/media/", [["d1440", "light", "en"], ["p390", "light", "en"]], { actions: [{ type: ["input[type=search]", "Thailand 2026"] }, { wait: 900 }] }),
  J("media_selected", "/media/", [["d1440", "light", "en"], ["p390", "light", "en"]], { actions: [{ click: ".mtile:nth-child(1) .mtile-check" }, { click: ".mtile:nth-child(2) .mtile-check" }, { shiftclick: ".mtile:nth-child(5) .mtile-btn" }, { wait: 300 }] }),
  J("media_upload", "/media/", [["d1440", "light", "en"], ["p390", "light", "en"]], { s: { slowUpload: true }, actions: [{ files: ["input[type=file][accept='image/*']", "ORIG12"] }, { wait: 1800 }] }),
  J("media_viewer", "/media/", [["d1440", "light", "en"], ["p390", "dark", "en"]], { actions: [{ click: ".mtile:nth-child(3) .mtile-btn" }, { wait: 800 }] }),
  J("media_menu", "/media/", [["d1440", "light", "en"]], { actions: [{ click: ".mtile:nth-child(1) .mtile-check" }, { click: "button[aria-label='Add to collection']" }, { wait: 300 }] }),
  J("media_organize", "/media/", [["d1440", "light", "en"]], { s: { slowUpload: false }, actions: [{ files: ["input[type=file][accept='image/*']", "ORIG14X3"] }, { wait: 6000 }] }),
];
const browser = await chromium.launch({ channel: "chrome" });
const report = [];
for (const j of jobs) {
  if (ONLY && !j.name.includes(ONLY)) continue;
  for (const [sz, scheme, locale] of j.combos) {
    const [w, h] = SIZES[sz];
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme, locale: locale === "es" ? "es-ES" : "en-US", deviceScaleFactor: 1 });
    await ctx.addInitScript(([t, loc, clear]) => { try { localStorage.setItem("vmk_auth_tokens", JSON.stringify(t)); if (loc) localStorage.setItem("vmk_locale", loc); localStorage.setItem("vmk_media_privacy_seen", "1"); if (clear) sessionStorage.removeItem("vmk_tasks"); } catch {} }, [tokens, locale === "es" ? "es" : "en", !!j.clearCache]);
    if (j.name === "media_empty" || j.name === "media") await ctx.addInitScript(() => { if (location.pathname.startsWith("/media") && !sessionStorage.getItem("seenp")) { try { localStorage.removeItem("vmk_media_privacy_seen"); sessionStorage.setItem("seenp", "1"); } catch {} } });
    await setup(ctx, j.s || {});
    const page = await ctx.newPage();
    const errs = [];
    page.on("console", (m) => { if (m.type() === "error") errs.push(m.text().slice(0, 200)); });
    page.on("pageerror", (e) => errs.push("pageerror " + String(e).slice(0, 200)));
    try {
      await page.goto(BASE + j.path, { waitUntil: j.noIdle ? "domcontentloaded" : "networkidle", timeout: 25000 });
      await page.waitForTimeout(j.wait || 1000);
      for (const a of j.actions || []) {
        if (a.click) await page.locator(a.click).first().click({ timeout: 5000 });
        if (a.hover) await page.locator(a.hover).first().hover({ timeout: 5000 });
        if (a.fill) await page.locator(a.fill[0]).first().fill(a.fill[1]);
        if (a.type) { const l = page.locator(a.type[0]).first(); await l.focus(); await l.pressSequentially(a.type[1], { delay: 15 }); }
        if (a.shiftclick) { await page.keyboard.down("Shift"); await page.locator(a.shiftclick).first().click({ timeout: 5000 }); await page.keyboard.up("Shift"); }
        if (a.files) { const n = a.files[1]; const m = /^ORIG(\d+)(X(\d+))?$/.exec(n); const list = origs.slice(0, Number(m[1])); const all = m[3] ? Array.from({ length: Number(m[3]) }, () => list).flat() : list; await page.locator(a.files[0]).first().setInputFiles(all.map((p, i) => ({ name: `IMG_${i}.jpg`, mimeType: "image/jpeg", buffer: fs.readFileSync(p) }))); }
        if (a.wait) await page.waitForTimeout(a.wait);
      }
      const file = path.join(OUT, `${j.name}__${sz}__${scheme}${locale === "es" ? "__es" : ""}.png`);
      await page.screenshot({ path: file, fullPage: false });
      report.push(`${path.basename(file)} ${errs.length ? "ERR " + errs.join(" | ") : "ok"}`);
    } catch (e) { report.push(`${j.name} ${sz} FAILED ${String(e).slice(0, 200)}`); }
    await ctx.close();
  }
}
await browser.close();
console.log(report.join("\n"));
