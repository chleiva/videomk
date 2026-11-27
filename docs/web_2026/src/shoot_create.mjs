// The Create screen redesign (docs/design_bar/CREATE_SCREEN_REDESIGN_BRIEF.md) against a MOCKED API: every state as a JPEG at 390, 768 and 1440 px (light, dark, English, Spanish),
// the 200% zoom and large-text fallbacks, keyboard focus, and behaviour checks (roles, names, order, contrast, sizes, what is sent).
//   1. python3 docs/web_2026/src/look_caps.py <scratch>/looks.json
//   2. cd frontend && npm run build && python3 -m http.server 4399 -d dist --bind 127.0.0.1
//   3. LOOKS=<scratch>/looks.json node docs/web_2026/src/shoot_create.mjs <out-dir> [only-substring|checks]
// Needs playwright-core (PLAYWRIGHT=path to its index.mjs) and Google Chrome. ONE headless browser, closed at the end. Nothing here talks to AWS.
import fs from "fs";
import path from "path";
const { chromium } = await import(process.env.PLAYWRIGHT || "/Users/chleiva/code/incident-command-agent/node_modules/playwright-core/index.mjs");
const OUT = process.argv[2] || "shots", ONLY = process.argv[3] || "";
const BASE = process.env.BASE || "http://127.0.0.1:4399";
const LOOKS = JSON.parse(fs.readFileSync(process.env.LOOKS, "utf8"));
fs.mkdirSync(OUT, { recursive: true });
const SIZES = { d1440: [1440, 900, 1], t768: [768, 1024, 1], p390: [390, 844, 2] };
const b64 = (o) => Buffer.from(JSON.stringify(o)).toString("base64url");
const tokens = { access_token: "a", id_token: `${b64({ alg: "none" })}.${b64({ sub: "user-1" })}.x`, refresh_token: "r", expires_at: Date.now() + 5 * 3600e3 };
const now = Date.now(), iso = (h) => new Date(now - h * 3600e3).toISOString();
const PICS = LOOKS.en.look.options.map((o) => Buffer.from(o.preview.split(",")[1], "base64"));   // four real 320x180 frames: the mock's thumbnails and photos
const T = (i) => `https://thumbs.test/${i % PICS.length}.jpg`;

const caps = (loc, s) => {
  const looks = JSON.parse(JSON.stringify(LOOKS[loc]));
  // the tile notes and the Spanish name the design review asked the server for (one line, no full stop; "Animado"): the server change is in flight, so the mock
  // carries them unless OLD_STRINGS=1. The web renders whatever arrives.
  if (!process.env.OLD_STRINGS) { const N = { en: { auto: "Picked for your topic", real: "Photos and footage", whiteboard: "Drawn by hand", cartoon: "Characters explain it" }, es: { auto: "Elegido según tu tema", real: "Fotos y video", whiteboard: "Dibujado a mano", cartoon: "Personajes lo explican" } };
    for (const o of looks.look.options) { o.note = N[loc][o.id] ?? o.note; if (loc === "es" && o.id === "cartoon") o.label = "Animado"; if (o.id === "auto") o.label = "Auto"; } }
  for (const [id, patch] of Object.entries(s.tiles || {})) Object.assign(looks.look.options.find((o) => o.id === id), patch);
  const plan = s.plan ? { plan: { id: "free", name: "Free", limits: { max_seconds: 30, resolutions: ["720p", "1080p"] }, plans: [{ id: "free", name: "Free" }, { id: "pro", name: "Pro" }, { id: "max", name: "Max" }] }, free_creation: s.freeCreation || "welcome", free: s.free || { available: true }, can_upgrade: false } : {};
  const ALL = ["16:9", "9:16", "1:1", "4:5"];
  return {
    aspects: [{ id: "16:9", label: loc === "es" ? "Horizontal" : "Landscape", ready: true }, { id: "9:16", label: "Vertical", ready: true }, { id: "1:1", label: loc === "es" ? "Cuadrado" : "Square", ready: true }, { id: "4:5", label: loc === "es" ? "Retrato" : "Portrait", ready: true }],
    resolutions: [{ id: "720p", label: "720p", credits_multiplier: 1, aspects: ALL, available: true, requires_plan: null }, { id: "1080p", label: "1080p", credits_multiplier: 1, aspects: ALL, available: true, requires_plan: null }, { id: "2160p", label: "4K", credits_multiplier: 2, aspects: ALL, available: !s.plan, requires_plan: s.plan ? "max" : null }],
    platforms: [{ id: "youtube", label: "YouTube", aspect: "16:9", resolution: "1080p", recommended_minutes: 3, max_minutes: null, supports_4k: true }, { id: "tiktok", label: "TikTok", aspect: "9:16", resolution: "1080p", recommended_minutes: 0.5, max_minutes: 3, supports_4k: false }, { id: "other", label: "Just a video", aspect: "16:9", resolution: "1080p", recommended_minutes: 1, max_minutes: null, supports_4k: true }],
    languages: [{ id: "en", label: "English" }, { id: "es", label: "Español" }],
    lengths: { min_minutes: 0.25, max_minutes: 12, presets: [0.25, 0.5, 0.75, 1, 2, 3, 5, 8, 12], ...(s.plan ? { plan_max_seconds: 30, plan_max_minutes: 0.5, locked: [{ feature: "length", over_seconds: 30, max_seconds: 300, requires_plan: "pro" }, { feature: "length", over_seconds: 300, max_seconds: 720, requires_plan: "max" }] } : {}) },
    max_photos: 100, intake: true, deck: { max_mb: 50, max_slides: 60, formats: ["pptx", "pdf"] }, ...(s.noLooks ? {} : { looks }), ...plan,
  };
};
const making = { scene_total: 6, scene_done: 2, live_line: "Adding footage of sunlit canopies", narration_line: "Sunlight pours through the canopy, and the forest breathes.", scenes: [1, 2, 3, 4, 5, 6].map((i) => ({ index: i, done: i <= 2, ...(i <= 2 ? { thumb_url: T(i) } : {}) })) };
const NOTE = { en: "Made from your photos: the Cartoon look is not used with your own photos.", es: "Hecho con tus fotos: el estilo Dibujos animados no se usa con tus propias fotos." };
const videos = (s) => [
  ...(s.cancelled ? [{ video_id: "v1", title: "How a forest breathes", status: "CANCELLED", created_at: iso(0.1), can_retry: true }] : [{ video_id: "v1", title: "How a forest breathes", status: "ASSETS_CREATION", created_at: iso(0.1), eta_seconds: 150, making }]),
  { video_id: "v2", title: "Why the sky is blue", status: "COMPLETE", created_at: iso(2), duration_s: 91, editable: true, preview_gif_url: T(1), look: { chosen: "auto", applied: "whiteboard", recipe: "whiteboard", cast: [], extras: [], why: "A step-by-step idea is clearest drawn.", by: "auto" } },
  { video_id: "v3", title: "How bees make honey", status: "COMPLETE", created_at: iso(5), duration_s: 62, editable: true, preview_gif_url: T(3), look: { chosen: "cartoon", applied: "cartoon", recipe: "conversation_board", cast: ["fox", "bear"], extras: ["board"], why: "You chose it.", by: "you" } },
  { video_id: "v4", title: "The history of the printing press", status: "COMPLETE", created_at: iso(30), duration_s: 182, preview_gif_url: T(2) },
].filter((v) => !(s.deleted || []).includes(v.video_id));
const gallery = (loc) => ({ videos: [["forest", loc === "es" ? "Cómo respira un bosque" : "How a forest breathes", "16:9", 28, 1], ["bees", loc === "es" ? "Cómo hacen miel las abejas" : "How bees make honey", "16:9", 30, 3], ["board", loc === "es" ? "El interés compuesto, dibujado" : "Compound interest, drawn", "16:9", 24, 2]].map(([id, title, aspect, seconds, i]) => ({ id, title, aspect, seconds, video_url: `https://thumbs.test/${id}.mp4`, poster_url: T(i) })), count: 3, expires_in: 3600 });

async function setup(ctx, s, loc, log) {
  await ctx.route(/thumbs\.test/, (r) => { const m = /\/(\d+)\.jpg/.exec(r.request().url()); return m ? r.fulfill({ status: 200, contentType: "image/jpeg", body: PICS[Number(m[1]) % PICS.length], headers: { "access-control-allow-origin": "*" } }) : r.fulfill({ status: 404 }); });
  await ctx.route(/vmk-assets\.s3\.amazonaws\.com/, (r) => r.fulfill({ status: 204, headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "*" } }));
  let up = 0;
  await ctx.route(/backend\.videomk\.com/, async (route) => {
    const req = route.request(), u = req.url(), m = req.method();
    const json = (o, st = 200) => route.fulfill({ status: st, contentType: "application/json", headers: { "access-control-allow-origin": "*" }, body: JSON.stringify(o) });
    if (m === "OPTIONS") return route.fulfill({ status: 204, headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*" } });
    if (m !== "GET") log.push({ m, u: u.replace(/^https:\/\/[^/]+/, ""), body: (() => { try { return JSON.parse(req.postData() || "null"); } catch { return null; } })() });
    if (u.endsWith("/gallery")) return json(s.galleryEmpty ? { videos: [] } : gallery(loc));
    if (u.includes("/capabilities")) return json(caps(loc, s));
    if (u.includes("/wallet")) return json({ balance: s.balance ?? 12, unlimited: false, buckets: s.plan ? [{ kind: "plan", remaining: s.balance ?? 12, expires_at: Math.floor(now / 1000) + 20 * 86400 }] : [], next_daily_at: null, ...(s.plan ? { plan: caps(loc, s).plan, free_creation: s.freeCreation || "welcome", free: s.free || { available: true }, can_upgrade: false } : {}) });
    if (u.includes("/videos/brief")) { if (s.briefDelay) await new Promise((r) => setTimeout(r, s.briefDelay)); return json({ status: "ok", brief: {} }); }
    if (u.endsWith("/videos/generate")) return s.generate ? json(s.generate[1], s.generate[0]) : json({ message: "workflow started", video_id: "v1", ...(s.note ? { note: NOTE[loc], look: { chosen: "cartoon", applied: "real", enforced: false, reason: "own_photos" } } : {}) }, 202);
    if (/\/videos\/v\d+\/cancel$/.test(u)) { s.cancelled = true; return json({ message: "cancelled", video_id: "v1", status: "CANCELLED", retries: 0, refunded: 2 }); }
    if (/\/videos\/v\d+$/.test(u) && m === "DELETE") { (s.deleted ||= []).push(u.split("/").pop()); return json({ message: "deleted" }); }
    if (/\/videos\/v1$/.test(u)) return json({ message: "not ready", status: "ASSETS_CREATION", making }, 409);
    if (/\/videos\/v\d+$/.test(u)) { const v = videos(s).find((x) => u.endsWith(x.video_id)); return json({ url: "https://thumbs.test/none.mp4", title: v?.title, description: "Why the sky looks blue, in ninety seconds.", look: v?.look }); }
    if (/\/videos$/.test(u)) return json({ items: s.noVideos ? [] : videos(s) });
    if (/\/uploads$/.test(u)) return json({ uploads: [{ id: "d" + ++up, url: "https://vmk-assets.s3.amazonaws.com/", fields: { key: `uploads/user-1/${up}.jpg` } }] });
    return json({}, 404);
  });
}

// ---------------------------------------------------------------- states
const SIZES2 = { p390: [390, 844, 2], t768: [768, 1024, 1], d1440: [1440, 900, 1], z1440: [720, 450, 2], z390: [195, 422, 2], short: [390, 560, 2], r320: [320, 640, 2], t150: [390, 844, 2] };
Object.assign(SIZES, SIZES2);
const TEXT = { en: "How bees make honey, for curious kids", es: "Cómo hacen miel las abejas, para niños curiosos" };
const fill = [{ fill: true }];
const photos = (n) => [{ files: n }, { wait: 2200 }];
const open = [{ click: ".look-pill" }, { wait: 350 }];
const pick = (id) => [{ click: `[data-look=${id}]` }, { wait: 250 }];
const face = (...ids) => ids.flatMap((id) => [{ click: `[data-face=${id}]` }, { wait: 120 }]);
const cartoon = [...fill, ...open, ...pick("cartoon"), ...face("fox", "bear"), { key: "Escape" }, { wait: 250 }];
const LEN = "button[aria-label='Length'], button[aria-label='Duración']";
const OPT = "button[aria-label='Options'], button[aria-label='Opciones']";
const FOR = "button[aria-label='Made for'], button[aria-label='Hecho para']";
const MAIN = ["p390", "t768", "d1440"];
const STANDARD = [["light", "en"], ["dark", "en"], ["light", "es"]];
const ST = [
  ["01_empty_first_video", "Empty, a first-time account: the field, three example chips, ONE row of pills, ONE tool row (photo, mic, Options, inactive Create), the first-video caption. No helper line.", "/new/", { noVideos: true }, []],
  ["02_empty_returning", "Empty, an account with finished videos: no chips, no caption (the balance is in the header chip).", "/new/", {}, []],
  ["03_typing", "Typing: Create is active (gradient, small shadow).", "/new/", {}, fill],
  ["04_with_photos", "Three photos attached: the strip, the count badge on the photo button.", "/new/", {}, [...fill, ...photos(3)]],
  ["05_recording", "Voice: the mic is a filled Stop, Listening... in the tool row, photo and Options disabled, Create inactive, the field read-only.", "/new/", { noVideos: true }, [{ click: "button[aria-label='Dictate'], button[aria-label='Dictar']" }, { wait: 500 }]],
  ["06_creating", "Creating: the dock is replaced by the full-width live capsule with Cancel; the prompt is dimmed and locked.", "/new/", { briefDelay: 9000 }, [...fill, { click: ".compose-go" }, { wait: 700 }]],
  ["07_look_cast_auto", "A look with a cast (Cartoon), characters left to us: the Characters pill appears as the fourth pill (a second pill row).", "/new/", {}, [...fill, ...open, ...pick("cartoon"), { key: "Escape" }, { wait: 250 }]],
  ["08_look_cast_two", "Cartoon with two characters: the Characters pill shows the faces.", "/new/", {}, cartoon],
  ["09_cast_surface", "The Characters pill opened: the same surface as the Look pill, the focus on the cast.", "/new/", {}, [...cartoon, { click: ".cast-pill" }, { wait: 350 }]],
  ["10_options_sheet", "Options: quality, subtitles, narration language, colors, watermark. No Format, no look tiles.", "/new/", {}, [...fill, { click: OPT }, { wait: 350 }]],
  ["11_for_menu", "The For menu: platforms, then the shapes no platform starts with.", "/new/", {}, [...fill, { click: FOR }, { wait: 250 }]],
  ["12_length_plan_locked", "Plan states: lengths the plan does not make are shown with the plan, not selectable.", "/new/", { plan: true }, [...fill, { click: LEN }, { wait: 250 }]],
  ["13_inactive_tap", "A tap on the inactive Create: it says what is missing, in place, and puts the caret back in the field.", "/new/", { noVideos: true }, [{ click: ".compose-go" }, { wait: 350 }]],
  ["14_error_plan_refusal", "An error from the server: its own sentence in place, the draft kept.", "/new/", { generate: [403, { code: "plan_length", message: "Videos on your plan can be up to 0:30 long. Pro makes longer ones.", plan: "free", requires_plan: "pro", can_upgrade: false }] }, [...fill, { click: ".compose-go" }, { wait: 900 }]],
  ["15_not_enough_credits", "Not enough credits: the sentence and the link to Credits; the caption steps aside.", "/new/", { balance: 0 }, [...fill, { wait: 300 }]],
  ["16_create_locked", "Locked plan state: an account that cannot create here sees the server's sentence and the showcase.", "/new/", { plan: true, balance: 0, free: { available: false, reason: "app_only", message: "Free videos are made in the VideoMK app. Get the app to make yours." } }, []],
  ["17_focus_create", "Keyboard: focus ring on Create (Tab from the field through the pills and tools).", "/new/", {}, [...fill, { focus: "#create-text" }, ...Array(7).fill({ key: "Tab" }), { wait: 150 }]],
  ["18_focus_pill", "Keyboard: focus ring on a pill.", "/new/", {}, [...fill, { focus: "#create-text" }, { key: "Tab" }, { key: "Tab" }, { wait: 150 }]],
];
const FALLBACKS = ["01_empty_first_video", "03_typing", "05_recording", "10_options_sheet", "07_look_cast_auto"];
const jobs = [];
for (const [name, title, p, s, actions] of ST) {
  const combos = MAIN.flatMap((sz) => STANDARD.map(([sc, l]) => [sz, sc, l]));
  if (FALLBACKS.includes(name)) combos.push(["z1440", "light", "en"], ["z390", "light", "en"], ["r320", "light", "en"], ["t150", "light", "en"], ["t150", "dark", "es"]);
  if (name === "16_create_locked") jobs.push({ name, title, path: p, s, actions, combos: MAIN.flatMap((sz) => STANDARD.map(([sc, l]) => [sz, sc, l])) });
  else jobs.push({ name, title, path: p, s, actions, combos });
}
for (const j of jobs) j.s = { balance: 11, ...j.s };

const browser = await chromium.launch({ channel: "chrome", headless: true });
const report = [];
async function context(sz, scheme, loc, s, log, job = {}) {
  const [w, h, dpr] = SIZES[sz];
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme, locale: loc === "es" ? "es-ES" : "en-US", deviceScaleFactor: dpr, reducedMotion: "reduce" });
  await ctx.addInitScript(([t, l, big]) => {
    try { localStorage.setItem("vmk_auth_tokens", JSON.stringify(t)); localStorage.setItem("vmk_locale", l); } catch {}
    // the browser has no speech service in a test run: a stand-in that "hears" a few words, so the recording state can be drawn
    window.SpeechRecognition = window.webkitSpeechRecognition = class { start() { setTimeout(() => this.onresult?.({ results: [Object.assign([{ transcript: "How bees make honey and" }], { isFinal: false })] }), 80); } stop() { setTimeout(() => this.onend?.(), 10); } };
    if (big) document.addEventListener("DOMContentLoaded", () => { document.documentElement.style.fontSize = "150%"; });
  }, [tokens, loc, sz === "t150"]);
  await setup(ctx, s, loc, log);
  return ctx;
}
async function act(page, a, loc) {
  if (a.click) await page.locator(a.click).first().click({ timeout: 6000, force: a.click.includes("compose-go") });   // an aria-disabled Create is still tappable: force skips Playwright's own "enabled" wait
  if (a.hover) await page.locator(a.hover).first().hover({ timeout: 6000 });
  if (a.focus) await page.locator(a.focus).first().focus();
  if (a.key) await page.keyboard.press(a.key);
  if (a.fill) await page.locator("#create-text").fill(TEXT[loc]);
  if (a.files) await page.locator("input[type=file][accept='image/*']").setInputFiles(Array.from({ length: a.files }, (_, i) => ({ name: `IMG_${i}.jpg`, mimeType: "image/jpeg", buffer: PICS[(i + 1) % PICS.length] })));
  if (a.wait) await page.waitForTimeout(a.wait);
}
// nothing truncated, nothing wider than the screen, no control over another or outside the card, every touch target big enough
const AUDIT = () => {
  const vis = (e) => e.offsetParent !== null || getComputedStyle(e).position === "fixed";
  const cut = [...document.querySelectorAll(".pill-v, .look-pill-v, .cast-pill-v, .tool-options-label, .compose-balance, .hint, .create-capsule span, .tool-listening")].filter((e) => vis(e) && e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflow !== "visible").map((e) => e.className + ":" + e.textContent.slice(0, 24));
  const card = document.querySelector(".composer-card:not(.create-locked)")?.getBoundingClientRect();
  const ctl = [...document.querySelectorAll(".composer-pills .pill, .tool-cluster button, .compose-go, .create-capsule")].filter(vis).map((e) => [e.className.split(" ").slice(0, 2).join("."), e.getBoundingClientRect()]).filter(([, r]) => r.width > 0);
  const hit = (a, b) => a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1;
  const over = [];
  ctl.forEach(([n, r], i) => { if (card && (r.left < card.left - 1 || r.right > card.right + 1)) over.push(n + " out"); ctl.slice(i + 1).forEach(([m, q]) => { if (hit(r, q)) over.push(n + "x" + m); }); });
  const small = [...document.querySelectorAll(".composer-pills .pill, .tool-cluster button, .compose-go")].filter(vis).filter((e) => e.getBoundingClientRect().width < 43.5 || e.getBoundingClientRect().height < 43.5).map((e) => e.className.split(" ")[0] + " " + Math.round(e.getBoundingClientRect().width) + "x" + Math.round(e.getBoundingClientRect().height));
  return { cut, over, small, wide: document.documentElement.scrollWidth - window.innerWidth };
};
const ONLYMODE = ONLY === "checks";
if (!ONLYMODE) for (const j of jobs) {
  if (ONLY && !j.name.includes(ONLY)) continue;
  for (const [sz, scheme, loc] of j.combos) {
    if (process.env.COMBO && !`${sz}__${scheme}__${loc}`.includes(process.env.COMBO)) continue;
    const s = JSON.parse(JSON.stringify(j.s || {})), log = [];
    const ctx = await context(sz, scheme, loc, s, log, j);
    const page = await ctx.newPage();
    const errs = [];
    page.on("console", (m) => { if (m.type() === "error" && !/none\.mp4|ERR_|Failed to load resource/.test(m.text())) errs.push(m.text().slice(0, 160)); });
    page.on("pageerror", (e) => errs.push("pageerror " + String(e).slice(0, 160)));
    const file = `${j.name}__${sz}__${scheme}__${loc}.jpg`;
    try {
      await page.goto(BASE + j.path, { waitUntil: "networkidle", timeout: 25000 });
      await page.waitForTimeout(700);
      for (const a of j.actions || []) await act(page, a, loc);
      for (const sel of [".look-pop", ".vm-pop", ".vm-menu-list"]) { const el = page.locator(sel); if (await el.count()) { await el.first().evaluate((e) => e.scrollIntoView({ block: "nearest" })); break; } }
      await page.waitForTimeout(150);
      const bad = await page.evaluate(AUDIT);
      if (process.env.EVAL) console.log(file, JSON.stringify(await page.evaluate(process.env.EVAL)));
      await page.screenshot({ path: path.join(OUT, file), type: "jpeg", quality: 88, fullPage: false });
      const kb = Math.round(fs.statSync(path.join(OUT, file)).size / 1024);
      report.push(`${file} ${kb} KB ${errs.length ? "ERR " + errs.join(" | ") : "ok"}${bad.cut.length ? " CUT " + bad.cut.join(",") : ""}${bad.wide > 0 ? " WIDE " + bad.wide : ""}${bad.over.length ? " OVERLAP " + bad.over.join(",") : ""}${bad.small.length ? " SMALL " + bad.small.join(",") : ""}`);
    } catch (e) { report.push(`${file} FAILED ${String(e).slice(0, 220)}`); }
    await ctx.close();
  }
}

// ---------------------------------------------------------------- behaviour checks (same browser, mocked API)
const checks = [];
const check = (name, ok, detail = "") => checks.push(`${ok ? "PASS" : "FAIL"} ${name}${ok ? "" : " :: " + detail}`);
async function run(name, s, fn, sz = "p390", scheme = "light", loc = "en") {
  if (ONLY && !ONLYMODE) return;
  const log = [], ctx = await context(sz, scheme, loc, { balance: 11, ...s }, log);
  const page = await ctx.newPage();
  try { await fn(page, log); } catch (e) { check(name, false, String(e).slice(0, 240)); }
  await ctx.close();
}
const go = async (page, p = "/new/") => { await page.goto(BASE + p, { waitUntil: "networkidle" }); await page.waitForTimeout(500); };
const gen = (log) => log.find((x) => x.u.endsWith("/videos/generate"))?.body;
const lum = (c) => { const [r, g, b] = c.match(/[\d.]+/g).slice(0, 3).map(Number).map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
const rows = (page, sel) => page.evaluate((q) => { const t = [...document.querySelectorAll(q)].filter((e) => e.offsetParent).map((e) => e.getBoundingClientRect().top).sort((x, y) => x - y); return t.filter((v, i) => i === 0 || v - t[i - 1] > 10).length; }, sel);

for (const sz of ["p390", "t768", "d1440"]) await run(`structure ${sz}`, { noVideos: true }, async (page) => {
  await go(page);
  check(`${sz}: the prompt has the focus on arrival (autofocus kept)`, await page.evaluate(() => document.activeElement?.id === "create-text"));
  check(`${sz}: ONE row of pills (three pills), the tool row below it`, (await rows(page, ".composer-pills .pill")) === 1 && (await page.locator(".composer-pills .pill").count()) === 3 && await page.evaluate(() => document.querySelector(".composer-pills").getBoundingClientRect().bottom <= document.querySelector(".composer-tools").getBoundingClientRect().top + 1));
  check(`${sz}: photo, mic, Options and Create share ONE row, Create last at the trailing end`, await page.evaluate(() => { const rs = [".tool-cluster .icon-btn:nth-child(1), .tool-cluster .tool > button", ".tool-cluster button[aria-label='Dictate']", ".tool-options", ".compose-go"].map((s) => document.querySelector(s)?.getBoundingClientRect()); if (rs.some((r) => !r)) return false; const t = rs.map((r) => Math.round(r.top + r.height / 2)); const card = document.querySelector(".composer-card").getBoundingClientRect(); return Math.max(...t) - Math.min(...t) <= 2 && rs[3].left > rs[2].right && card.right - rs[3].right < 40; }));
  check(`${sz}: Create is a compact pill: 48 high, at least 112 wide`, await page.evaluate(() => { const r = document.querySelector(".compose-go").getBoundingClientRect(); return Math.round(r.height) === 48 && r.width >= 111.5 && r.width < 200; }));
  check(`${sz}: every pill has a leading glyph (an svg before its text)`, await page.evaluate(() => [...document.querySelectorAll(".composer-pills .pill")].every((p) => p.firstElementChild?.tagName.toLowerCase() === "svg")));
  check(`${sz}: no helper line (the field's own placeholder is the only instruction) and no Characters pill for Auto`, await page.evaluate(() => !/Describe it in a sentence|Describe your video/.test([...document.querySelectorAll(".composer-card p, .composer-card .hint")].filter((e) => e.offsetParent && !e.classList.contains("sr-only-vmk")).map((e) => e.textContent).join("|"))) && (await page.locator(".cast-pill").count()) === 0);
  check(`${sz}: touch targets of the dock are at least 44 px`, (await page.evaluate(AUDIT)).small.length === 0, JSON.stringify((await page.evaluate(AUDIT)).small));
  check(`${sz}: nothing wider than the screen, nothing cut, nothing overlapping`, await page.evaluate(AUDIT).then((b) => b.wide <= 0 && b.cut.length === 0 && b.over.length === 0), JSON.stringify(await page.evaluate(AUDIT)));
  check(`${sz}: Tab order is reading order: field, For, Length, Look, photo, mic, Options, Create`, await (async () => {
    const seen = []; await page.locator("#create-text").focus();
    for (let i = 0; i < 7; i++) { await page.keyboard.press("Tab"); seen.push(await page.evaluate(() => document.activeElement?.getAttribute("aria-label") ?? "")); }
    return JSON.stringify(seen) === JSON.stringify(["Made for", "Length", "Look: Auto", "Add photos", "Dictate", "Options", "Create video"]);
  })(), "");
});
await run("sizes at 390 are exact", {}, async (page) => {
  await go(page);
  const m = await page.evaluate(() => { const b = (s) => document.querySelector(s).getBoundingClientRect(); return { pill: b(".composer-pills .pill").height, photo: b(".tool-cluster .vm-menu button").width, mic: b(".tool-cluster button[aria-label='Dictate']").height, opt: b(".tool-options").height, go: [b(".compose-go").width, b(".compose-go").height], pillsW: [...document.querySelectorAll(".composer-pills .pill")].map((e) => Math.round(e.getBoundingClientRect().width)), dock: b(".composer-bar").height }; });
  check("390: pills 44, photo/mic/Options 44, Create 48", m.pill === 44 && m.photo === 44 && m.mic === 44 && m.opt === 44 && Math.round(m.go[1]) === 48, JSON.stringify(m));
  check("390: dock about 124 px with one pill row (measured: " + Math.round(m.dock) + ")", m.dock >= 100 && m.dock <= 140, String(m.dock));
});
await run("chips and caption", { noVideos: true }, async (page) => {
  await go(page);
  const chips = await page.locator(".compose-examples .chip").count();
  check("a first-time account sees three example chips while the field is empty", chips === 3, String(chips));
  const cap = await page.locator(".compose-balance").textContent();
  check("the first-video caption teaches the price once, in words: '1 credit. You have 11.'", /^\d+ credits?\. You have 11\.$/.test(cap ?? ""), cap ?? "none");
  await page.locator(".compose-examples .chip").first().click(); await page.waitForTimeout(200);
  check("tapping a chip fills the field and the chips go", (await page.locator("#create-text").inputValue()) === "How bees make honey" && (await page.locator(".compose-examples").count()) === 0);
});
await run("chips short window", { noVideos: true }, async (page) => {
  await go(page);
  check("on a short window two chips show, not three", await page.evaluate(() => [...document.querySelectorAll(".compose-examples .chip")].filter((e) => e.offsetParent).length) === 2);
}, "short");
await run("returning account", {}, async (page) => {
  await go(page);
  check("an account with a finished video: no chips and no caption", (await page.locator(".compose-examples").count()) === 0 && (await page.locator(".compose-balance").count()) === 0);
});
await run("low balance", { balance: 1 }, async (page) => {
  await go(page); await page.locator("#create-text").fill(TEXT.en);
  const cap = await page.locator(".compose-balance").textContent().catch(() => null);
  check("a low balance (under two videos' worth) shows '1 credit left' under the tool row", cap === "1 credit left", String(cap));
});
await run("inactive create", { noVideos: true }, async (page, log) => {
  await go(page);
  const b = page.locator(".compose-go");
  check("empty prompt: Create is inactive but not disabled (aria-disabled, still focusable)", (await b.getAttribute("aria-disabled")) === "true" && (await b.getAttribute("disabled")) === null && (await b.evaluate((e) => { e.focus(); return document.activeElement === e; })));
  check("its name is 'Create video' and its state says why: 'Not ready: describe your video.'", (await b.getAttribute("aria-label")) === "Create video" && (await page.locator("#create-state").textContent()) === "Not ready: describe your video.");
  const cs = await b.evaluate((e) => { const c = getComputedStyle(e); return { fg: c.color, bg: c.backgroundColor, sh: c.boxShadow }; });
  check("inactive: opaque fill, no shadow, label contrast at least 4.5:1 (light)", ratio(cs.fg, cs.bg) >= 4.5 && cs.sh === "none" && !cs.bg.includes("rgba(0, 0, 0, 0)"), JSON.stringify(cs) + " " + ratio(cs.fg, cs.bg));
  await b.click({ force: true }); await page.waitForTimeout(250);
  check("a tap says what is missing, in place, and the caret goes back to the field; nothing is sent", (await page.locator(".hint", { hasText: "Describe your video to create it." }).count()) === 1 && (await page.evaluate(() => document.activeElement?.id === "create-text")) && !log.some((x) => x.u.endsWith("/videos/generate") || x.u.endsWith("/videos/brief")));
  await page.locator("#create-text").fill(TEXT.en);
  check("typing makes it active: not aria-disabled, the state says 'Ready, costs 1 credit.'", (await b.getAttribute("aria-disabled")) === null && /^Ready, costs \d+ credits?\.$/.test((await page.locator("#create-state").textContent()) ?? ""));
  const on = await b.evaluate((e) => { const c = getComputedStyle(e); return { bg: c.backgroundImage, fg: c.color }; });
  check("active: the gradient, a white label", /linear-gradient/.test(on.bg) && on.fg === "rgb(255, 255, 255)", JSON.stringify(on));
});
await run("inactive contrast dark", {}, async (page) => {
  await go(page);
  const cs = await page.locator(".compose-go").evaluate((e) => { const c = getComputedStyle(e); return { fg: c.color, bg: c.backgroundColor }; });
  check("inactive Create label contrast at least 4.5:1 (dark)", ratio(cs.fg, cs.bg) >= 4.5, JSON.stringify(cs) + " " + ratio(cs.fg, cs.bg));
}, "p390", "dark");
await run("voice", {}, async (page, log) => {
  await go(page);
  const mic = page.locator(".tool-cluster button[aria-label='Dictate']");
  await mic.click(); await page.waitForTimeout(400);
  check("recording: the mic is a Stop (named 'Stop dictating'), Listening… is in the tool row", (await page.locator(".tool-cluster button[aria-label='Stop dictating']").count()) === 1 && (await page.locator(".composer-tools .tool-listening").textContent()) === "Listening…");
  check("recording: photo and Options are disabled, Create is inactive, the field is read-only and shows the words", (await page.locator(".tool-cluster .vm-menu button").isDisabled()) && (await page.locator(".tool-options").isDisabled()) && (await page.locator(".compose-go").getAttribute("aria-disabled")) === "true" && (await page.locator("#create-text").getAttribute("readonly")) !== null && (await page.locator("#create-text").inputValue()).startsWith("How bees"));
  check("recording: the state says to stop first", (await page.locator("#create-state").textContent()) === "Not ready: stop dictating first.");
  await page.locator(".compose-go").click({ force: true }); await page.waitForTimeout(300);
  check("recording: a tap on Create sends nothing", !log.some((x) => x.u.endsWith("/videos/generate") || x.u.endsWith("/videos/brief")));
  check("recording: the mic stays at the LEFT of Create", await page.evaluate(() => document.querySelector(".tool-cluster button[aria-label='Stop dictating']").getBoundingClientRect().right < document.querySelector(".compose-go").getBoundingClientRect().left));
  await page.locator(".tool-cluster button[aria-label='Stop dictating']").click(); await page.waitForTimeout(300);
  check("stopping: the mic, photo and Options are back, Create is active", (await page.locator(".tool-cluster button[aria-label='Dictate']").count()) === 1 && !(await page.locator(".tool-options").isDisabled()) && (await page.locator(".compose-go").getAttribute("aria-disabled")) === null);
});
await run("creating", { briefDelay: 6000 }, async (page, log) => {
  await go(page); await page.locator("#create-text").fill(TEXT.en);
  await page.locator(".compose-go").click(); await page.waitForTimeout(500);
  check("creating: the dock is replaced by the live capsule (status role, spinner, text, Cancel), the pills and Create are gone", (await page.locator(".create-capsule[role=status]").count()) === 1 && (await page.locator(".composer-pills").count()) === 0 && (await page.locator(".compose-go").count()) === 0 && (await page.locator(".create-capsule button", { hasText: "Cancel" }).count()) === 1);
  check("creating: the capsule is full width (the card's inner width) and 64 high", await page.evaluate(() => { const c = document.querySelector(".create-capsule").getBoundingClientRect(), f = document.querySelector(".composer-card").getBoundingClientRect(); return Math.round(c.height) >= 64 && f.width - c.width < 40; }));
  check("creating: the prompt is dimmed to 50% and locked (inert)", await page.evaluate(() => { const t = document.querySelector(".composer-top"); return getComputedStyle(t).opacity === "0.5" && t.hasAttribute("inert"); }));
  await page.locator(".create-capsule button").click(); await page.waitForTimeout(500);
  check("Cancel brings the dock back untouched: the text is kept, nothing was started", (await page.locator("#create-text").inputValue()) === TEXT.en && (await page.locator(".compose-go").count()) === 1 && !log.some((x) => x.u.endsWith("/videos/generate")));
});
await run("what is sent", {}, async (page, log) => {
  await go(page); await page.locator("#create-text").fill(TEXT.en); await page.locator(".compose-go").click(); await page.waitForTimeout(1000);
  const b = gen(log);
  check("the request is unchanged: text, platform, aspect, resolution, target_minutes, captions, language", !!b && typeof b.target_minutes === "number" && !!b.platform && !!b.aspect && !!b.resolution && b.captions === true && b.language === "auto", JSON.stringify(b));
});
await run("shape in the For menu", {}, async (page, log) => {
  await go(page); await page.locator("#create-text").fill(TEXT.en);
  await page.locator(FOR).click(); await page.waitForTimeout(150);
  const items = await page.locator(".vm-menu-item").allTextContents();
  check("For lists the platforms, then Square and Portrait (the Format row moved here)", items.join("|").includes("YouTube") && items.includes("Square") && items.includes("Portrait"), items.join("|"));
  await page.locator(".vm-menu-item", { hasText: "Square" }).click(); await page.waitForTimeout(150);
  check("choosing Square shows Square on the pill with a square glyph", (await page.locator(".composer-pills .pill").first().textContent())?.trim() === "Square" && await page.evaluate(() => !!document.querySelector(".composer-pills .pill svg rect[width='14']")));
  await page.locator(".compose-go").click(); await page.waitForTimeout(1000);
  check("... and 1:1 is what is sent", gen(log)?.aspect === "1:1", JSON.stringify(gen(log)));
});
await run("options sheet", {}, async (page) => {
  await go(page); await page.locator(OPT).click(); await page.waitForTimeout(300);
  const t = await page.locator(".opts").innerText();
  check("Options has no Format row and no look tiles; it keeps quality, subtitles, narration, colors", !/Format/.test(t) && (await page.locator(".opts .look-tile").count()) === 0 && /Quality|Resolution/.test(t) && /Subtitles/.test(t) && /Narration/.test(t) && /Colors/.test(t), t.replace(/\n/g, "|"));
  check("Options opens as a bottom sheet on a phone (fixed, at the bottom)", await page.evaluate(() => { const p = document.querySelector(".vm-pop"); const r = p.getBoundingClientRect(); return getComputedStyle(p).position === "fixed" && Math.abs(r.bottom - innerHeight) < 2; }));
});
await run("options popover desktop", {}, async (page) => {
  await go(page); await page.locator(OPT).click(); await page.waitForTimeout(300);
  check("on desktop Options opens to the right of its button, inside the window", await page.evaluate(() => { const r = document.querySelector(".vm-pop").getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth; }));
}, "d1440");
await run("cast pill", {}, async (page, log) => {
  await go(page); await page.locator("#create-text").fill(TEXT.en);
  check("Auto look: no Characters pill; the Look pill says the look only", (await page.locator(".cast-pill").count()) === 0 && (await page.locator(".look-pill-faces").count()) === 0);
  for (const a of [...open, ...pick("cartoon"), ...face("fox", "bear"), { key: "Escape" }, { wait: 250 }]) await act(page, a, "en");
  check("Cartoon: the Characters pill appears as the fourth pill, with the two faces; still never a fifth control", (await page.locator(".cast-pill").count()) === 1 && (await page.locator(".cast-pill .face-img").count()) === 2 && (await page.locator(".composer-pills .pill").count()) === 4);
  check("the pills wrap to a second row only now (about 172 px dock)", (await rows(page, ".composer-pills .pill")) === 2);
  check("its name says who: 'Characters: Fox and Bruno'", (await page.locator(".cast-pill").getAttribute("aria-label")) === "Characters: Fox and Bruno", await page.locator(".cast-pill").getAttribute("aria-label"));
  await page.locator(".cast-pill").click(); await page.waitForTimeout(350);
  check("the Characters pill opens the same surface with the focus on a face", (await page.locator(".look-pop").count()) === 1 && (await page.evaluate(() => !!document.activeElement?.getAttribute("data-face"))));
  await page.keyboard.press("Escape"); await page.waitForTimeout(200);
  check("Escape closes it and gives the focus back to the Characters pill", await page.evaluate(() => document.activeElement?.classList.contains("cast-pill")));
  await page.locator(".compose-go").click(); await page.waitForTimeout(900);
  const b = gen(log);
  check("what is sent: look cartoon, cast fox + bear (unchanged contract)", b?.look === "cartoon" && JSON.stringify(b.cast) === '["fox","bear"]', JSON.stringify(b));
});
await run("fallback stacked", {}, async (page) => {
  await go(page);
  check("at 320 px (reflow): Create is on its own full-width row, 52 px high, below the tools", await page.evaluate(() => { const g = document.querySelector(".compose-go").getBoundingClientRect(), c = document.querySelector(".tool-cluster").getBoundingClientRect(), row = document.querySelector(".composer-tools").getBoundingClientRect(); return Math.round(g.height) === 52 && g.top >= c.bottom - 1 && Math.abs(g.width - row.width) < 2; }));
  const b = await page.evaluate(AUDIT);
  check("at 320 px: nothing wider than the screen, cut or overlapping", b.wide <= 0 && b.cut.length === 0 && b.over.length === 0, JSON.stringify(b));
}, "r320");
await run("fallback large text", {}, async (page) => {
  await go(page);
  const g = await page.evaluate(() => { const g = document.querySelector(".compose-go").getBoundingClientRect(), row = document.querySelector(".composer-tools").getBoundingClientRect(); return { h: Math.round(g.height), full: Math.abs(g.width - row.width) < 2, mic: document.querySelector(".tool-cluster button[aria-label='Dictate']").getBoundingClientRect().left < row.left + row.width / 2 && document.querySelector(".tool-cluster button[aria-label='Dictate']").getBoundingClientRect().top < g.top }; });
  check("with text at 150%: Create drops to its own full-width row and the mic stays on the left", g.full && g.mic, JSON.stringify(g));
  const b = await page.evaluate(AUDIT);
  check("with text at 150%: nothing wider than the screen, cut or overlapping", b.wide <= 0 && b.cut.length === 0 && b.over.length === 0, JSON.stringify(b));
}, "t150");
await run("fallback zoom 200%", {}, async (page) => {
  await go(page);
  const b = await page.evaluate(AUDIT);
  check("at 200% zoom on a phone (195 css px): nothing wider than the screen, nothing overlapping", b.wide <= 0 && b.over.length === 0, JSON.stringify(b));
}, "z390");
await run("zoom 200% desktop", {}, async (page) => {
  await go(page);
  const b = await page.evaluate(AUDIT);
  check("at 200% zoom on desktop (720 css px): Create stays compact beside the tools, nothing cut or overlapping", b.wide <= 0 && b.over.length === 0 && b.cut.length === 0 && await page.evaluate(() => Math.round(document.querySelector(".compose-go").getBoundingClientRect().height) === 48), JSON.stringify(b));
}, "z1440");
await run("plan states", { plan: true }, async (page) => {
  await go(page); await page.locator("#create-text").fill(TEXT.en);
  await page.locator(LEN).click(); await page.waitForTimeout(200);
  check("a length the plan does not make cannot be chosen (and says which plan)", (await page.locator(".vm-menu-item.is-dim").count()) > 0 && (await page.locator(".plan-tag").count()) > 0);
});
await run("error in place", { generate: [403, { code: "plan_length", message: "Videos on your plan can be up to 0:30 long. Pro makes longer ones.", requires_plan: "pro", can_upgrade: false }] }, async (page) => {
  await go(page); await page.locator("#create-text").fill(TEXT.en); await page.locator(".compose-go").click(); await page.waitForTimeout(900);
  check("an error: the server's sentence in the status line, the draft kept, the dock is back, a live region says it", (await page.locator(".compose-notes[aria-live=polite] .hint-bad", { hasText: "Pro makes longer ones." }).count()) === 1 && (await page.locator("#create-text").inputValue()) === TEXT.en && (await page.locator(".compose-go").count()) === 1);
});
await run("not enough credits", { balance: 0 }, async (page, log) => {
  await go(page); await page.locator("#create-text").fill(TEXT.en);
  check("not enough credits: the sentence and the Credits link, no caption", (await page.locator(".hint", { hasText: "needs" }).count()) >= 1 && (await page.locator(".compose-balance").count()) === 0);
  await page.locator(".compose-go").click(); await page.waitForTimeout(400);
  check("... and a tap sends nothing", !log.some((x) => x.u.endsWith("/videos/generate")));
});
await run("spanish", { noVideos: true }, async (page) => {
  await go(page);
  const cap = await page.locator(".compose-balance").textContent();
  check("Spanish: caption '3 créditos. Tienes 11.', Options is 'Opciones', Create is 'Crear'", /^\d+ créditos?\. Tienes 11\.$/.test(cap ?? "") && (await page.locator(".tool-options-label").textContent()) === "Opciones" && (await page.locator(".compose-go span").first().textContent()) === "Crear", cap ?? "");
  check("Spanish: the state says it in words", (await page.locator("#create-state").textContent()) === "No está listo: describe tu video.");
  const b = await page.evaluate(AUDIT);
  check("Spanish at 390: nothing cut, wider or overlapping", b.wide <= 0 && b.cut.length === 0 && b.over.length === 0, JSON.stringify(b));
}, "p390", "light", "es");
await run("focus ring", {}, async (page) => {
  await go(page); await page.locator("#create-text").fill(TEXT.en); await page.locator("#create-text").focus();
  const rings = [];
  for (let i = 0; i < 7; i++) { await page.keyboard.press("Tab"); rings.push(await page.evaluate(() => { const c = getComputedStyle(document.activeElement); return c.outlineStyle !== "none" && parseFloat(c.outlineWidth) >= 2; })); }
  check("every stop of the dock has a visible focus ring (2 px or more)", rings.every(Boolean), JSON.stringify(rings));
});
await run("dark contrast of text on the dock", {}, async (page) => {
  await go(page); await page.locator("#create-text").fill(TEXT.en);
  const r = await page.evaluate(() => { const card = getComputedStyle(document.querySelector(".composer-card")).backgroundColor; const g = (s) => { const e = document.querySelector(s), host = e.closest(".pill, .tool-btn"); return [s, getComputedStyle(e).color, host ? getComputedStyle(host).backgroundColor : card]; }; return [".pill-v", ".tool-options", ".compose-text", ".compose-balance"].map((s) => (document.querySelector(s) ? g(s) : null)).filter(Boolean); });
  const bad = r.filter(([s, fg, bg]) => s !== ".compose-go" && ratio(fg, bg) < 4.5).map(([s, fg, bg]) => s + " " + ratio(fg, bg).toFixed(2));
  check("dark: pill, Options and prompt text at least 4.5:1 on their surfaces", bad.length === 0, bad.join(","));
}, "p390", "dark");

await browser.close();
console.log(report.join("\n"));
console.log("\n" + checks.join("\n"));
console.log(`\n${report.filter((r) => / ok$/.test(r)).length}/${report.length} shots clean, ${checks.filter((c) => c.startsWith("PASS")).length}/${checks.length} checks pass`);
