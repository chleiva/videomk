// WP-C screenshots: serves the built app (DIST), fakes the API in the browser, and captures each page and state of the watch page, credits, settings, feedback, sign-in and editor.
// usage: node shoot_c.mjs <outDir> [filter]   (needs playwright-core and Google Chrome)
import { chromium } from "playwright-core";
import fs from "fs"; import http from "http"; import path from "path";
const DIST = process.env.DIST, OUT = process.argv[2] || "shots", ONLY = process.argv[3] || "";
const LAND = process.env.LAND, TALL = process.env.TALL;
fs.mkdirSync(OUT, { recursive: true });
const mime = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".json": "application/json", ".webmanifest": "application/json", ".mjs": "text/javascript" };
const server = http.createServer((req, res) => {
  const u = new URL(req.url, "http://x"); let p = decodeURIComponent(u.pathname);
  if (p.endsWith("/")) p += "index.html"; else if (!path.extname(p)) p += "/index.html";
  const f = path.join(DIST, p);
  if (!f.startsWith(DIST) || !fs.existsSync(f)) { res.writeHead(404); res.end("nf"); return; }
  res.writeHead(200, { "content-type": mime[path.extname(f)] || "application/octet-stream" }); res.end(fs.readFileSync(f));
}).listen(4455);
const b64 = (o) => Buffer.from(JSON.stringify(o)).toString("base64url");
const idToken = `${b64({ alg: "none" })}.${b64({ sub: "user-1", email: "maria@example.com", auth_time: Math.floor(Date.now() / 1000) })}.x`;
const tokens = { access_token: "a", id_token: idToken, refresh_token: "r", expires_at: Date.now() + 3600e3 * 5 };
const now = Date.now();
const wallet = (o = {}) => ({ balance: 3, unlimited: false, buckets: [{ kind: "daily", remaining: 1, expires_at: Math.floor(now / 1000) + 3600 * 5 }, { kind: "signup", remaining: 2, expires_at: null }], next_daily_at: Math.floor(now / 1000) + 3600 * 20, ...o });
const wmView = (premium) => ({ watermark: { mode: "videomk", position: "auto", has_logo: false }, capabilities: { modes: [{ id: "none", available: true }, { id: "videomk", available: true }, { id: "custom", available: premium, requires: "premium" }], forced: false, premium, logo: { max_bytes: 2097152, types: ["image/png", "image/jpeg", "image/svg+xml"] } } });
const beat = (i, type, text) => ({ id: `b${i}`, narration: text, scene: { type, props: type === "title" ? { title: "How a forest breathes", subtitle: "Leaves, light and air" } : { items: ["Light", "Water", "Air"] } }, duration: 9 + i });
const plan = { video_id: "v2", rev: 3, status: "COMPLETE", edit_state: "READY", title: "How a forest breathes", description: "", theme: "midnight", mood: "calm", voice: "Ruth",
  beats: [beat(1, "title", "A forest breathes in carbon dioxide and breathes out the oxygen we need."), beat(2, "bullets", "Three things power every leaf: light, water and air."), beat(3, "bullets", "Forests absorb billions of tonnes of carbon dioxide every year.")],
  final: { url: "/land.mp4", rev: 3 }, preview: { url: null, rev: null }, limits: { max_beats: 40, min_words: 4, max_words: 60 }, scene_types: ["title", "bullets", "diagram", "chart", "timeline", "stat", "quote", "image"] };
const desc = "Chapters\n0:00 Intro\n0:12 Light\n0:40 Water\n\nPhoto credits\nForest path by Anna K. on Unsplash\nLeaves by Sam R. on Pexels";

async function setup(ctx, o) {
  await ctx.route(/127\.0\.0\.1:8787/, async (route) => {
    const u = route.request().url(), m = route.request().method();
    const json = (b, s = 200) => route.fulfill({ status: s, contentType: "application/json", headers: { "access-control-allow-origin": "*" }, body: JSON.stringify(b) });
    if (m === "OPTIONS") return route.fulfill({ status: 204, headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*" } });
    if (u.includes("/wallet")) return o.walletFail ? json({}, 500) : json(wallet(o.wallet));
    if (u.includes("/watermark") && m === "GET") return o.noWm ? json({}, 404) : json(wmView(!!o.premium));
    if (u.includes("/watermark")) return json({});
    if (u.includes("/account/delete")) return json({ apple: "not_linked" }, 202);
    if (u.includes("/plan")) return json(plan);
    const vm = u.match(/\/videos\/(v\d)(\?|$)/);
    if (vm) {
      if (o.watch === "making") return json({ status: "PLOT_CREATION" }, 409);
      if (o.watch === "failed") return json({ status: "ERROR" }, 409);
      if (o.watch === "error") return json({ message: "x" }, 500);
      return json({ video_id: vm[1], status: "COMPLETE", title: vm[1] === "v7" ? "A morning in the forest" : "How a forest breathes", description: desc, url: vm[1] === "v7" ? "/tall.mp4" : "/land.mp4" });
    }
    if (u.includes("/capabilities")) return json({ aspects: [], resolutions: [], platforms: [], languages: [], lengths: { min_minutes: 0.25, max_minutes: 12, presets: [1] } });
    if (u.includes("/feedback")) return json({}, 202);
    if (u.includes("/videos")) return json({ items: [] });
    return json({}, 404);
  });
  const serve = (file) => (r) => { // honours Range, so the video can seek
    const buf = fs.readFileSync(file), range = r.request().headers()["range"];
    if (range) { const m = /bytes=(\d*)-(\d*)/.exec(range); const a = Number(m[1] || 0), b = m[2] ? Number(m[2]) : buf.length - 1; return r.fulfill({ status: 206, contentType: "video/mp4", headers: { "accept-ranges": "bytes", "content-range": `bytes ${a}-${b}/${buf.length}` }, body: buf.subarray(a, b + 1) }); }
    return r.fulfill({ status: 200, contentType: "video/mp4", headers: { "accept-ranges": "bytes" }, body: buf });
  };
  await ctx.route("**/land.mp4", serve(LAND));
  await ctx.route("**/tall.mp4", serve(TALL));
}
const SIZES = { d: [1440, 900], t: [820, 1100], p: [390, 844] };
const items = [
  { id: "watch_ready", url: "/watch/?id=v2", auth: 1, sizes: "dp", after: async (pg) => { await pg.waitForSelector(".player video"); await pg.waitForTimeout(1200); } },
  { id: "watch_playing", url: "/watch/?id=v2", auth: 1, sizes: "d", after: async (pg) => { await pg.waitForSelector(".player video"); await pg.click(".player-big"); await pg.waitForTimeout(1500); await pg.mouse.move(700, 400); await pg.waitForTimeout(300); } },
  { id: "watch_tall", url: "/watch/?id=v7", auth: 1, sizes: "dp", after: async (pg) => { await pg.waitForSelector(".player video"); await pg.waitForTimeout(1200); } },
  { id: "watch_end", url: "/watch/?id=v2", auth: 1, sizes: "dp", after: async (pg) => { await pg.waitForSelector(".player video"); await pg.waitForTimeout(800); await pg.evaluate(async () => { const v = document.querySelector(".player video"); v.muted = true; v.currentTime = Math.max(0, v.duration - 0.4); await v.play().catch(() => {}); }); await pg.waitForSelector(".player-end", { timeout: 6000 }); await pg.waitForTimeout(500); } },
  { id: "watch_info", url: "/watch/?id=v2", auth: 1, sizes: "dp", after: async (pg) => { await pg.waitForSelector(".player video"); await pg.click('button[aria-label="Details"], button[aria-label="Detalles"]'); await pg.waitForTimeout(500); } },
  { id: "watch_more", url: "/watch/?id=v2", auth: 1, sizes: "dp", after: async (pg) => { await pg.waitForSelector(".player video"); await pg.click('button[aria-haspopup="menu"]'); await pg.waitForTimeout(400); } },
  { id: "watch_making", url: "/watch/?id=v2", auth: 1, sizes: "p", o: { watch: "making" }, after: async (pg) => pg.waitForSelector(".watch-state p") },
  { id: "watch_error", url: "/watch/?id=v2", auth: 1, sizes: "p", o: { watch: "error" }, after: async (pg) => pg.waitForSelector(".watch-state p") },
  { id: "credits", url: "/wallet/", auth: 1, sizes: "dp", after: async (pg) => pg.waitForSelector(".credits-num") },
  { id: "credits_how", url: "/wallet/", auth: 1, sizes: "p", after: async (pg) => { await pg.waitForSelector(".credits-num"); await pg.click(".credits-how-btn"); await pg.waitForTimeout(300); } },
  { id: "credits_unlimited", url: "/wallet/", auth: 1, sizes: "p", o: { wallet: { unlimited: true, buckets: [], next_daily_at: null } }, after: async (pg) => pg.waitForSelector(".credits-num") },
  { id: "settings", url: "/settings/", auth: 1, sizes: "dp", o: { premium: false }, after: async (pg) => { await pg.waitForSelector(".settings .srow"); await pg.waitForTimeout(500); } },
  { id: "settings_premium", url: "/settings/", auth: 1, sizes: "p", o: { premium: true }, after: async (pg) => { await pg.waitForSelector(".settings .srow"); await pg.waitForTimeout(500); } },
  { id: "settings_delete", url: "/settings/", auth: 1, sizes: "dp", after: async (pg) => { await pg.waitForSelector(".srow-danger"); await pg.click(".srow-danger"); await pg.fill("#delete-word", "DELETE"); await pg.waitForTimeout(400); } },
  { id: "settings_done", url: "/settings/", auth: 1, sizes: "p", after: async (pg) => { await pg.waitForSelector(".srow-danger"); await pg.click(".srow-danger"); await pg.fill("#delete-word", "DELETE"); await pg.click(".btn-danger"); await pg.waitForSelector(".done-card"); await pg.waitForTimeout(300); } },
  { id: "feedback", url: "/feedback/", auth: 1, sizes: "dp", after: async (pg) => pg.waitForSelector("textarea") },
  { id: "feedback_report", url: "/feedback/?from=report&kind=problem&video=v2", auth: 1, sizes: "p", after: async (pg) => { await pg.waitForSelector("textarea"); await pg.fill("textarea", "The voice cuts off at the end."); await pg.waitForTimeout(200); } },
  { id: "feedback_thanks", url: "/feedback/", auth: 1, sizes: "p", after: async (pg) => { await pg.waitForSelector("textarea"); await pg.fill("textarea", "Please add more voices."); await pg.click("button[type=submit]"); await pg.waitForSelector("[role=status] h1"); await pg.waitForTimeout(300); } },
  { id: "signin", url: "/signin/", auth: 0, sizes: "dp", after: async (pg) => pg.waitForSelector(".pbtn") },
  { id: "editor", url: "/edit/?id=v2", auth: 1, sizes: "dp", after: async (pg) => { await pg.waitForSelector(".scene-card"); await pg.waitForSelector(".player video"); await pg.waitForTimeout(800); } },
];
const browser = await chromium.launch({ channel: "chrome" });
for (const it of items) {
  if (ONLY && !it.id.includes(ONLY)) continue;
  for (const sz of it.sizes) for (const scheme of ["light", "dark"]) for (const loc of (it.id === "signin" || it.id.startsWith("settings") || it.id === "credits" ? ["en", "es"] : ["en"])) {
    if (loc === "es" && scheme === "dark" && sz !== "p") continue;
    const [w, h] = SIZES[sz];
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme, locale: loc === "es" ? "es-ES" : "en-US", deviceScaleFactor: 1 });
    if (it.auth) await ctx.addInitScript((t) => { try { localStorage.setItem("vmk_auth_tokens", JSON.stringify(t)); } catch {} }, tokens);
    await setup(ctx, it.o || {});
    const page = await ctx.newPage();
    page.on("pageerror", (e) => console.log("PAGEERROR", it.id, e.message));
    try { await page.goto("http://127.0.0.1:4455" + it.url, { waitUntil: "load" }); await it.after(page); await page.waitForTimeout(250); await page.screenshot({ path: path.join(OUT, `${it.id}_${sz}_${scheme}_${loc}.png`) }); }
    catch (e) { console.log("FAIL", it.id, sz, scheme, loc, String(e.message).split("\n")[0]); try { await page.screenshot({ path: path.join(OUT, `FAIL_${it.id}_${sz}_${scheme}_${loc}.png`) }); } catch {} }
    await ctx.close();
  }
}
await browser.close(); server.close();
