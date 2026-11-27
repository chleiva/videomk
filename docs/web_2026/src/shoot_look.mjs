// The look picker and what came with it (plan locks, the note, cancel, delete with undo), against a MOCKED API: every state as a JPEG, and behaviour checks.
//   1. python3 docs/web_2026/src/look_caps.py <scratch>/looks.json     (the server's own capabilities.looks, EN and ES, real previews and faces)
//   2. cd frontend && npm run build && python3 -m http.server 4399 -d dist --bind 127.0.0.1
//   3. LOOKS=<scratch>/looks.json node docs/web_2026/src/shoot_look.mjs docs/web_2026/look_picker [only-substring]
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
    if (u.includes("/videos/brief")) return json({ status: "ok", brief: {} });
    if (u.endsWith("/videos/generate")) return s.generate ? json(s.generate[1], s.generate[0]) : json({ message: "workflow started", video_id: "v1", ...(s.note ? { note: NOTE[loc], look: { chosen: "cartoon", applied: "real", enforced: false, reason: "own_photos" } } : {}) }, 202);
    if (/\/videos\/v\d+\/cancel$/.test(u)) { s.cancelled = true; return json({ message: "cancelled", video_id: "v1", status: "CANCELLED", retries: 0, refunded: 2 }); }
    if (/\/videos\/v\d+$/.test(u) && m === "DELETE") { (s.deleted ||= []).push(u.split("/").pop()); return json({ message: "deleted" }); }
    if (/\/videos\/v1$/.test(u)) return json({ message: "not ready", status: "ASSETS_CREATION", making }, 409);
    if (/\/videos\/v\d+$/.test(u)) { const v = videos(s).find((x) => u.endsWith(x.video_id)); return json({ url: "https://thumbs.test/none.mp4", title: v?.title, description: "Why the sky looks blue, in ninety seconds.", look: v?.look }); }
    if (/\/videos$/.test(u)) return json({ items: videos(s) });
    if (/\/uploads$/.test(u)) return json({ uploads: [{ id: "d" + ++up, url: "https://vmk-assets.s3.amazonaws.com/", fields: { key: `uploads/user-1/${up}.jpg` } }] });
    return json({}, 404);
  });
}

// ---- small steps the jobs are written with
const TEXT = { en: "How bees make honey, for curious kids", es: "Cómo hacen miel las abejas, para niños curiosos" };
const open = [{ click: ".look-pill" }, { wait: 350 }];
const pick = (id) => [{ click: `[data-look=${id}]` }, { wait: 250 }];
const face = (...ids) => ids.flatMap((id) => [{ click: `[data-face=${id}]` }, { wait: 120 }]);
const photos = (n) => [{ files: n }, { wait: 2200 }];
const fill = [{ fill: true }];
const J = (name, p, combos, extra = {}) => ({ name, path: p, combos, ...extra });
const L = ["d1440", "light", "en"], D = ["d1440", "dark", "en"], P = ["p390", "light", "en"], PD = ["p390", "dark", "en"], TB = ["t768", "light", "en"], ES = ["d1440", "light", "es"], PES = ["p390", "light", "es"];
const WITH_NOTE = { note: true, seedNote: true };
const jobs = [
  J("01_pill_auto", "/new/", [L, D, P], { actions: fill }),
  J("02_open_auto", "/new/", [L, D, TB, P, PD, ES, PES], { actions: [...fill, ...open] }),
  J("03_cartoon_cast_auto", "/new/", [L, P], { actions: [...fill, ...open, ...pick("cartoon")] }),
  J("04_cartoon_one", "/new/", [L], { actions: [...fill, ...open, ...pick("cartoon"), ...face("fox")] }),
  J("05_conversation_board", "/new/", [L, D, TB, P, PD, ES, PES], { actions: [...fill, ...open, ...pick("cartoon"), ...face("fox", "bear"), { click: "#look-extra-board" }, { wait: 200 }] }),
  J("06_cast_full", "/new/", [L, P], { actions: [...fill, ...open, ...pick("cartoon"), ...face("ines", "fox", "owl")] }),
  J("07_pill_cartoon", "/new/", [L, D, P, PES, TB], { actions: [...fill, ...open, ...pick("cartoon"), ...face("fox", "bear"), { key: "Escape" }, { wait: 250 }] }),
  J("07b_pill_three_faces", "/new/", [L, ES, ["t768", "light", "es"], ["t768", "dark", "en"], PES], { actions: [...fill, ...open, ...pick("cartoon"), ...face("ines", "fox", "owl"), { key: "Escape" }, { wait: 250 }] }),
  J("08_pill_whiteboard", "/new/", [L, PES], { actions: [...fill, ...open, ...pick("whiteboard"), { wait: 200 }] }),
  J("09_locked_by_plan", "/new/", [L, PD], { s: { plan: true, tiles: { cartoon: { allowed: false, requires_plan: "pro" }, whiteboard: { available: false } } }, actions: [...fill, ...open] }),
  J("10_with_photos", "/new/", [L, P], { actions: [...fill, ...photos(3), ...open] }),
  J("11_reset_after_photos", "/new/", [L, P, ES], { actions: [...fill, ...open, ...pick("cartoon"), ...face("fox"), { key: "Escape" }, ...photos(2)] }),
  J("12_keyboard_focus", "/new/", [L, D], { actions: [...fill, { focus: ".look-pill" }, { key: "Enter" }, { wait: 300 }, { key: "ArrowRight" }, { key: "ArrowRight" }, { wait: 200 }] }),
  J("13_keyboard_cast", "/new/", [L], { actions: [...fill, { focus: ".look-pill" }, { key: "Enter" }, { wait: 300 }, { key: "End" }, { key: " " }, { wait: 300 }, { key: "Tab" }, { key: "ArrowRight" }, { key: "ArrowRight" }, { key: " " }, { key: "ArrowRight" }, { wait: 200 }] }),
  J("14_hint_conversation_short", "/new/", [L, P], { actions: [...fill, { click: "button[aria-label='Length'], button[aria-label='Duración']" }, { click: "text=15 s" }, ...open, ...pick("cartoon"), ...face("fox", "bear"), { key: "Escape" }, { wait: 250 }] }),
  J("15_hint_best_shape", "/new/", [L], { actions: [...fill, { click: "button[aria-label='Made for']" }, { click: "text=TikTok" }, ...open, ...pick("whiteboard"), { wait: 250 }] }),
  J("16_no_picker_old_server", "/new/", [L], { s: { noLooks: true }, actions: [...fill, { click: "button[aria-label='Look']" }, { wait: 250 }] }),
  J("20_plan_lengths_locked", "/new/", [L, P, ES], { s: { plan: true }, actions: [...fill, { click: "button[aria-label='Length'], button[aria-label='Duración']" }, { wait: 250 }] }),
  J("21_plan_4k_locked", "/new/", [L], { s: { plan: true }, actions: [...fill, { click: "button[aria-label='Made for']" }, { click: "text=YouTube" }, { click: "button[aria-label='Options']" }, { wait: 300 }] }),
  J("22_plan_refusal_in_place", "/new/", [L, P], { s: { generate: [403, { code: "plan_length", message: "Videos on your plan can be up to 0:30 long. Pro makes longer ones.", plan: "free", requires_plan: "pro", can_upgrade: false }] }, actions: [...fill, { click: ".compose-go" }, { wait: 900 }] }),
  J("23_free_budget_spent", "/new/", [L], { s: { generate: [429, { code: "free_budget_spent", message: "Today's free videos are used up for everyone. They are back tomorrow. Your credits are untouched.", can_upgrade: false }] }, actions: [...fill, { click: ".compose-go" }, { wait: 900 }] }),
  J("24_create_locked_gallery", "/new/", [L, D, P, ES, PES], { s: { plan: true, balance: 0, free: { available: false, reason: "app_only", message: null } }, freeMsg: { en: "Free videos are made in the VideoMK app. Get the app to make yours.", es: "Los videos gratis se hacen en la app de VideoMK. Descárgala para hacer el tuyo." }, wait: 1200 }),
  J("30_making_note_cancel", "/generations/", [L, D, P, PES], { s: WITH_NOTE }),
  J("31_cancel_question", "/generations/", [L, P], { s: WITH_NOTE, actions: [{ click: ".mkb-cancel" }, { wait: 400 }] }),
  J("32_cancelled", "/generations/", [L], { s: WITH_NOTE, actions: [{ click: ".mkb-cancel" }, { wait: 300 }, { click: ".dialog-actions .btn-danger" }, { wait: 900 }] }),
  J("33_video_menu_delete", "/generations/", [L], { actions: [{ hover: ".vtile:nth-child(1)" }, { click: ".vtile:nth-child(1) .vtile-more" }, { wait: 250 }] }),
  J("34_deleted_undo", "/generations/", [L, D, P, PES], { actions: [{ hover: ".vtile:nth-child(1)" }, { click: ".vtile:nth-child(1) .vtile-more" }, { click: ".vm-menu-item.is-danger" }, { wait: 500 }] }),
  J("40_watch_details_look", "/watch/?id=v3", [L, P], { actions: [{ click: "button[aria-label='More']" }, { click: "text=Details" }, { wait: 900 }] }),
  J("41_watch_more_delete", "/watch/?id=v2", [L], { actions: [{ click: "button[aria-label='More']" }, { wait: 300 }] }),
  J("42_watch_making_note", "/watch/?id=v1", [L, P], { s: WITH_NOTE }),
  J("50_credits_plan", "/wallet/", [L, P], { s: { plan: true } }),
];

// ---- REVIEW=1: the set for a design review. Every state of the look and cast feature at 390, 768 and 1440, light and dark, plus Spanish, at 2x, with an index.md
const REVIEW = !!process.env.REVIEW;
if (REVIEW) {
  for (const k of Object.keys(SIZES)) SIZES[k][2] = 2;
  const reopen = [{ wait: 200 }, ...open];
  const R = [
    ["01_create_look_control", "Create, the Look control at rest (Auto)", "/new/", { actions: fill }],
    ["02_look_auto", "Picker open, Auto selected (the default)", "/new/", { actions: [...fill, ...open] }],
    ["03_look_real", "Picker open, Real selected", "/new/", { actions: [...fill, ...open, ...pick("real"), ...reopen] }],
    ["04_look_whiteboard", "Picker open, Whiteboard selected", "/new/", { actions: [...fill, ...open, ...pick("whiteboard"), ...reopen] }],
    ["05_look_cartoon_cast_0", "Cartoon selected: the cast appears in the same surface, none chosen (Auto cast), board off", "/new/", { actions: [...fill, ...open, ...pick("cartoon")] }],
    ["06_cast_1", "Cast: one character chosen (its role and topic underneath)", "/new/", { actions: [...fill, ...open, ...pick("cartoon"), ...face("fox")] }],
    ["07_cast_2_conversation", "Cast: two chosen, the conversation note, numbered in the order picked", "/new/", { actions: [...fill, ...open, ...pick("cartoon"), ...face("fox", "bear")] }],
    ["08_cast_3_full", "Cast: three chosen (the maximum), the others dimmed", "/new/", { actions: [...fill, ...open, ...pick("cartoon"), ...face("ines", "fox", "owl")] }],
    ["09_board_on", "Hand-drawn board switch on (two characters)", "/new/", { actions: [...fill, ...open, ...pick("cartoon"), ...face("fox", "bear"), { click: "#look-extra-board" }, { wait: 200 }] }],
    ["10_pill_cartoon_chosen", "Create after choosing Cartoon with two characters: the pill shows the look and the faces", "/new/", { actions: [...fill, ...open, ...pick("cartoon"), ...face("fox", "bear"), { key: "Escape" }, { wait: 250 }] }],
    ["11_not_allowed_and_unavailable", "Cartoon not allowed on the plan (locked, plan name), Whiteboard not available on this stage (hidden)", "/new/", { s: { plan: true, tiles: { cartoon: { allowed: false, requires_plan: "pro" }, whiteboard: { available: false } } }, actions: [...fill, ...open] }],
    ["12_with_photos", "Photos attached: only the looks made from photos are offered, one line says why", "/new/", { actions: [...fill, ...photos(3), ...open] }],
    ["13_reset_after_photos", "Photos attached after choosing Cartoon: back to Auto with one line", "/new/", { actions: [...fill, ...open, ...pick("cartoon"), ...face("fox"), { key: "Escape" }, ...photos(2)] }],
    ["14_keyboard_focus_tile", "Keyboard: opened with Enter, two presses of the right arrow, focus ring on Whiteboard (Auto still chosen)", "/new/", { actions: [...fill, { focus: ".look-pill" }, { key: "Enter" }, { wait: 300 }, { key: "ArrowRight" }, { key: "ArrowRight" }, { wait: 200 }] }],
    ["15_keyboard_focus_cast", "Keyboard: Cartoon chosen with Space, Tab to the cast, arrows to a face (focus ring)", "/new/", { actions: [...fill, { focus: ".look-pill" }, { key: "Enter" }, { wait: 300 }, { key: "End" }, { key: " " }, { wait: 300 }, { key: "Tab" }, { key: "ArrowRight" }, { key: "ArrowRight" }, { key: " " }, { key: "ArrowRight" }, { wait: 200 }] }],
    ["16_making_note", "Videos while making: the server's note that the look was adapted, and Cancel", "/generations/", { s: WITH_NOTE }],
    ["17_watch_making_note", "The video page while making: the same note", "/watch/?id=v1", { s: WITH_NOTE }],
    ["18_video_page_look", "The video page, Details: the look the video got", "/watch/?id=v3", { actions: [{ click: "button[aria-label='More'], button[aria-label='Más']" }, { click: "text=/^(Details|Detalles)$/" }, { wait: 900 }] }],
  ];
  const combos = Object.keys(SIZES).flatMap((sz) => [[sz, "light", "en"], [sz, "dark", "en"], [sz, "light", "es"]]);
  jobs.length = 0;
  for (const [name, title, p, extra] of R) jobs.push({ name, title, path: p, combos, ...extra });
}

const browser = await chromium.launch({ channel: "chrome", headless: true });
const report = [];
async function context(sz, scheme, loc, s, log, job = {}) {
  const [w, h, dpr] = SIZES[sz];
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme, locale: loc === "es" ? "es-ES" : "en-US", deviceScaleFactor: dpr, reducedMotion: "reduce" });
  await ctx.addInitScript(([t, l, note]) => { try { localStorage.setItem("vmk_auth_tokens", JSON.stringify(t)); localStorage.setItem("vmk_locale", l); if (note) localStorage.setItem("vmk_look_notes", JSON.stringify([["v1", note]])); } catch {} }, [tokens, loc, s.seedNote ? NOTE[loc] : null]);
  if (job.freeMsg) s.free = { ...s.free, message: job.freeMsg[loc] };
  await setup(ctx, s, loc, log);
  return ctx;
}
async function act(page, a, loc) {
  if (a.click) await page.locator(a.click).first().click({ timeout: 6000 });
  if (a.hover) await page.locator(a.hover).first().hover({ timeout: 6000 });
  if (a.focus) await page.locator(a.focus).first().focus();
  if (a.key) await page.keyboard.press(a.key);
  if (a.fill) await page.locator("#create-text").fill(TEXT[loc]);
  if (a.files) await page.locator("input[type=file][accept='image/*']").setInputFiles(Array.from({ length: a.files }, (_, i) => ({ name: `IMG_${i}.jpg`, mimeType: "image/jpeg", buffer: PICS[(i + 1) % PICS.length] })));
  if (a.wait) await page.waitForTimeout(a.wait);
}
for (const j of jobs) {
  if (ONLY && !j.name.includes(ONLY)) continue;
  for (const [sz, scheme, loc] of j.combos) {
    const s = JSON.parse(JSON.stringify(j.s || {})), log = [];
    const ctx = await context(sz, scheme, loc, s, log, j);
    const page = await ctx.newPage();
    const errs = [];
    page.on("console", (m) => { if (m.type() === "error" && !/none\.mp4|ERR_|Failed to load resource/.test(m.text())) errs.push(m.text().slice(0, 160)); });
    page.on("pageerror", (e) => errs.push("pageerror " + String(e).slice(0, 160)));
    const file = `${j.name}__${sz}__${scheme}__${loc}.jpg`;
    try {
      await page.goto(BASE + j.path, { waitUntil: "networkidle", timeout: 25000 });
      await page.waitForTimeout(j.wait || 700);
      for (const a of j.actions || []) await act(page, a, loc);
      const pop = page.locator(".look-pop");
      if (await pop.count()) await pop.evaluate((el) => el.scrollIntoView({ block: "nearest" }));
      await page.waitForTimeout(150);
      // nothing truncated, nothing wider than the screen
      const bad = await page.evaluate(() => {
        const cut = [...document.querySelectorAll(".look-name, .look-note, .face-name, .look-pill span, .look-line, .look-extra-name, .look-extra-note, .plan-tag, .locked-msg, .locked-plan, .mkb-note, .composer-pills .pill > span")].filter((e) => e.offsetParent && e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflow !== "visible").map((e) => e.className + ":" + e.textContent.slice(0, 24));
        // no control of the composer bar over another, none outside the card
        const card = document.querySelector(".composer-card:not(.create-locked)")?.getBoundingClientRect();
        const ctl = [...document.querySelectorAll(".composer-tools > *, .composer-pills > *, .compose-go")].map((e) => [e.className.split(" ")[0] || e.tagName, e.getBoundingClientRect()]).filter(([, r]) => r.width > 0);
        const hit = (a, b) => a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1;
        const over = [];
        ctl.forEach(([n, r], i) => { if (card && (r.left < card.left - 1 || r.right > card.right + 1)) over.push(n + " out"); ctl.slice(i + 1).forEach(([m, q]) => { if (hit(r, q)) over.push(n + "x" + m); }); });
        return { cut, over, wide: document.documentElement.scrollWidth - window.innerWidth };
      });
      await page.screenshot({ path: path.join(OUT, file), type: "jpeg", quality: REVIEW ? 90 : 80, fullPage: false });
      const kb = Math.round(fs.statSync(path.join(OUT, file)).size / 1024);
      report.push(`${file} ${kb} KB ${errs.length ? "ERR " + errs.join(" | ") : "ok"}${bad.cut.length ? " CUT " + bad.cut.join(",") : ""}${bad.wide > 0 ? " WIDE " + bad.wide : ""}${bad.over.length ? " OVERLAP " + bad.over.join(",") : ""}${kb > 300 && !REVIEW ? " TOO BIG" : ""}`);
    } catch (e) { report.push(`${file} FAILED ${String(e).slice(0, 220)}`); }
    await ctx.close();
  }
}

// ---------------------------------------------------------------- behaviour checks (same browser, mocked API)
const checks = [];
const check = (name, ok, detail = "") => checks.push(`${ok ? "PASS" : "FAIL"} ${name}${ok ? "" : " :: " + detail}`);
async function run(name, s, fn, sz = "d1440") {
  if (REVIEW || (ONLY && !"checks".includes(ONLY))) return;
  const log = [], ctx = await context(sz, "light", "en", s, log);
  const page = await ctx.newPage();
  try { await fn(page, log, s); } catch (e) { check(name, false, String(e).slice(0, 200)); }
  await ctx.close();
}
const gen = (log) => log.find((x) => x.u.endsWith("/videos/generate"))?.body;
const go = async (page, p = "/new/") => { await page.goto(BASE + p, { waitUntil: "networkidle" }); await page.waitForTimeout(500); };
const send = async (page) => { await page.locator(".compose-go").click(); await page.waitForTimeout(900); };

await run("auto", {}, async (page, log) => {
  await go(page); await page.locator("#create-text").fill(TEXT.en); await send(page);
  const b = gen(log), brief = log.find((x) => x.u.endsWith("/videos/brief"))?.body;
  check("Auto sends no look, cast, extras or style (generate and brief)", !!b && !("look" in b) && !("cast" in b) && !("extras" in b) && !("style" in b) && !!brief && !("look" in brief.options), JSON.stringify(b));
});
await run("cartoon", {}, async (page, log) => {
  await go(page); await page.locator("#create-text").fill(TEXT.en);
  for (const a of [...open, ...pick("cartoon"), ...face("fox", "bear"), { click: "#look-extra-board" }, { click: ".look-panel .btn" }]) await act(page, a, "en");
  check("Done closes the surface and gives the focus back to the pill", (await page.locator(".look-pop").count()) === 0 && (await page.evaluate(() => document.activeElement?.classList.contains("look-pill"))));
  await send(page);
  const b = gen(log), brief = log.find((x) => x.u.endsWith("/videos/brief"))?.body;
  check("Cartoon + Fox + Bruno + board: look, cast (ids in order), extras in generate", b?.look === "cartoon" && JSON.stringify(b.cast) === '["fox","bear"]' && JSON.stringify(b.extras) === '["board"]', JSON.stringify(b));
  check("... and the same three keys in the options of brief", brief?.options?.look === "cartoon" && JSON.stringify(brief.options.cast) === '["fox","bear"]' && JSON.stringify(brief.options.extras) === '["board"]', JSON.stringify(brief));
  await go(page);
  check("the last choice is remembered on this device", (await page.locator(".look-pill-v").textContent()) === "Cartoon" && (await page.locator(".look-pill-faces .face-img").count()) === 2);
});
await run("keyboard", {}, async (page, log) => {
  await go(page); await page.locator("#create-text").fill(TEXT.en);
  await page.locator(".look-pill").focus(); await page.keyboard.press("Enter"); await page.waitForTimeout(250);
  check("Enter on the pill opens it with the focus on the chosen tile", await page.evaluate(() => document.activeElement?.getAttribute("data-look") === "auto"));
  await page.keyboard.press("ArrowRight"); await page.keyboard.press("ArrowRight");
  check("arrow keys move between tiles without choosing", await page.evaluate(() => document.activeElement?.getAttribute("data-look") === "whiteboard" && document.querySelector('[data-look="auto"]').getAttribute("aria-checked") === "true"));
  check("the focused tile has a visible focus ring", await page.evaluate(() => { const c = getComputedStyle(document.activeElement); return c.outlineStyle !== "none" && parseFloat(c.outlineWidth) >= 2; }));
  await page.keyboard.press("ArrowLeft"); await page.keyboard.press("ArrowLeft"); await page.keyboard.press("ArrowLeft");
  check("the arrows wrap around", await page.evaluate(() => document.activeElement?.getAttribute("data-look") === "cartoon"));
  await page.keyboard.press(" "); await page.waitForTimeout(250);
  check("Space chooses Cartoon and the cast appears in the same surface", (await page.locator(".look-cast").count()) === 1 && (await page.locator('[data-look="cartoon"]').getAttribute("aria-checked")) === "true");
  await page.keyboard.press("Tab");
  check("Tab goes from the tiles to the cast (one stop each)", await page.evaluate(() => document.activeElement?.classList.contains("face-auto")));
  for (let i = 0; i < 5; i++) await page.keyboard.press("ArrowRight");
  await page.keyboard.press("Enter"); await page.waitForTimeout(150);
  check("arrows walk the faces and Enter ticks one", (await page.locator('[data-face="fox"]').getAttribute("aria-pressed")) === "true");
  await page.keyboard.press("Tab");
  check("the next stop is the board switch", await page.evaluate(() => document.activeElement?.id === "look-extra-board"));
  await page.keyboard.press(" ");
  await page.keyboard.press("Escape"); await page.waitForTimeout(200);
  check("Escape closes and gives the focus back to the pill", (await page.locator(".look-pop").count()) === 0 && (await page.evaluate(() => document.activeElement?.classList.contains("look-pill"))));
  await page.locator(".look-pill").press("Enter"); await page.waitForTimeout(200); await page.keyboard.press("Home"); await page.keyboard.press("ArrowRight"); await page.keyboard.press("Enter"); await page.waitForTimeout(250);
  check("a look with nothing more to decide (Real) closes on Enter: pick and go", (await page.locator(".look-pop").count()) === 0 && (await page.locator(".look-pill-v").textContent()) === "Real");
  await page.locator("#create-text").focus(); await page.keyboard.press("Control+Enter"); await page.waitForTimeout(900);
  const b = gen(log);
  check("the keyboard-only choice is what is sent (Real: look only)", b?.look === "real" && !("cast" in b) && !("extras" in b), JSON.stringify(b));
});
await run("photos", { note: true }, async (page, log) => {
  await go(page); await page.locator("#create-text").fill(TEXT.en);
  for (const a of [...open, ...pick("cartoon"), ...face("fox"), { key: "Escape" }, ...photos(2)]) await act(page, a, "en");
  check("attaching photos after choosing Cartoon resets the look to Auto, with one line", (await page.locator(".look-pill-v").textContent()) === "Auto" && (await page.locator("text=The look is back to Auto.").count()) === 1);
  await act(page, { click: ".look-pill" }, "en"); await page.waitForTimeout(250);
  check("with photos only Auto and Real are offered", (await page.locator(".look-tile").count()) === 2);
  await page.keyboard.press("Escape"); await send(page);
  const b = gen(log);
  check("the request then has the photos and no look", Array.isArray(b?.media) && b.media.length === 2 && !("look" in b) && !("cast" in b), JSON.stringify(b));
  await page.waitForURL(/generations/, { timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(900);
  check("the server's note is shown on the Making banner", (await page.locator(".mkb-note").textContent().catch(() => ""))?.includes("Cartoon look is not used"));
});
await run("old server", { noLooks: true }, async (page, log) => {
  await go(page); await page.locator("#create-text").fill(TEXT.en);
  check("without looks.look there is no picker: the Look pill is the colour theme, as before", (await page.locator(".look-pill").count()) === 0 && (await page.locator("button[aria-label='Look']").count()) === 1);
  await send(page);
  const b = gen(log);
  check("... and the request is what it was", !!b && !("look" in b) && !("cast" in b) && b.target_minutes === 1, JSON.stringify(b));
});
await run("plan refusal", { generate: [403, { code: "plan_length", message: "Videos on your plan can be up to 0:30 long. Pro makes longer ones.", requires_plan: "pro", can_upgrade: false }] }, async (page) => {
  await go(page); await page.locator("#create-text").fill(TEXT.en); await send(page);
  check("403 plan_length: the server's sentence in place, the draft kept, no upgrade button", (await page.locator("text=Pro makes longer ones.").count()) === 1 && (await page.locator("#create-text").inputValue()) === TEXT.en && (await page.locator("text=/upgrade|buy/i").count()) === 0 && page.url().includes("/new"));
});
await run("plan lengths", { plan: true }, async (page, log) => {
  await go(page); await page.locator("#create-text").fill(TEXT.en);
  check("the plan's longest video is the default length", (await page.locator("button[aria-label='Length']").textContent())?.includes("30 s"));
  await page.locator("button[aria-label='Length']").click(); await page.waitForTimeout(200);
  await page.locator(".vm-menu-item", { hasText: "5 min" }).click({ force: true }); await page.waitForTimeout(200);
  check("a locked length cannot be chosen", (await page.locator("button[aria-label='Length']").first().textContent())?.includes("30 s"));
});
await run("delete undo", {}, async (page, log) => {
  await go(page, "/generations/");
  const n = await page.locator(".vtile").count();
  await page.locator(".vtile").first().hover(); await page.locator(".vtile-more").first().click(); await page.locator(".vm-menu-item.is-danger").click(); await page.waitForTimeout(400);
  check("Delete: the card leaves at once and the toast says Deleted · Undo", (await page.locator(".vtile").count()) === n - 1 && (await page.locator(".toast").textContent())?.includes("Deleted") && (await page.locator(".toast button").textContent()) === "Undo");
  await page.locator(".toast button").click(); await page.waitForTimeout(900);
  check("Undo brings it back and nothing was sent to the server", (await page.locator(".vtile").count()) === n && !log.some((x) => x.m === "DELETE"));
  await page.locator(".vtile").first().hover(); await page.locator(".vtile-more").first().click(); await page.locator(".vm-menu-item.is-danger").click();
  await page.waitForTimeout(7200);
  check("without Undo the video is deleted when the toast is gone (DELETE .../videos/{id})", log.filter((x) => x.m === "DELETE" && /\/videos\/v2$/.test(x.u)).length === 1 && (await page.locator(".vtile").count()) === n - 1);
});
await run("delete then leave", {}, async (page) => {
  // a request made while the page is being left is not seen by the mock, so the page's own fetch is watched: what was asked for, with keepalive, is written down
  await page.addInitScript(() => { const f = window.fetch; window.fetch = (u, o = {}) => { if (o.method === "DELETE") { try { localStorage.setItem("probe_delete", JSON.stringify([String(u), o.keepalive === true, !!o.headers?.Authorization])); } catch {} } return f(u, o); }; });
  await go(page, "/generations/");
  await page.locator(".vtile").first().hover(); await page.locator(".vtile-more").first().click(); await page.locator(".vm-menu-item.is-danger").click(); await page.waitForTimeout(300);
  await page.goto(BASE + "/wallet/", { waitUntil: "networkidle" }); await page.waitForTimeout(600);
  const probe = JSON.parse((await page.evaluate(() => localStorage.getItem("probe_delete"))) || "null");
  check("leaving the page before the Undo time is over still sends the delete (keepalive, signed)", !!probe && /\/videos\/v2$/.test(probe[0]) && probe[1] === true && probe[2] === true, JSON.stringify(probe));
});
await run("watch delete", {}, async (page, log) => {
  await go(page, "/watch/?id=v2");
  await page.locator("button[aria-label='More']").click(); await page.locator("text=Delete video").click();
  await page.waitForURL(/generations/, { timeout: 5000 }); await page.waitForTimeout(900);
  check("Delete video on Watch goes to Videos with the same Deleted · Undo toast", (await page.locator(".toast").textContent().catch(() => ""))?.includes("Deleted") && (await page.locator(".vtile-title", { hasText: "Why the sky is blue" }).count()) === 0 && !log.some((x) => x.m === "DELETE"));
});
await run("cancel", {}, async (page, log) => {
  await go(page, "/generations/");
  await page.locator(".mkb-cancel").click(); await page.waitForTimeout(300);
  check("Cancel asks once, and the safe answer has the focus", await page.evaluate(() => document.activeElement?.textContent === "Keep making"));
  await page.locator(".dialog-actions .btn-danger").click(); await page.waitForTimeout(1000);
  check("Stop sends POST .../cancel and says the credits are back", log.some((x) => x.m === "POST" && /\/videos\/v1\/cancel$/.test(x.u)) && (await page.locator(".toast").textContent())?.includes("2 credits are back"));
  check("the video is then a stopped card that can be tried again or removed", (await page.locator(".mkb").count()) === 0 && (await page.locator("text=You cancelled this video.").count()) === 1 && (await page.locator(".vtile.is-failed button", { hasText: "Try again" }).count()) === 1);
});
await run("locked create", { plan: true, balance: 0, free: { available: false, reason: "app_only", message: "Free videos are made in the VideoMK app." } }, async (page) => {
  await go(page);
  check("a Free account that cannot create here sees the locked card and the showcase, never the form", (await page.locator(".create-locked").count()) === 1 && (await page.locator("#create-text").count()) === 0 && (await page.locator(".show-tile").count()) === 3 && (await page.locator("text=/upgrade|buy/i").count()) === 0);
});
await run("free with credits", { plan: true, balance: 3, free: { available: false, reason: "app_only", message: "x" } }, async (page) => {
  await go(page);
  check("the same account with credits to spend gets the normal Create", (await page.locator("#create-text").count()) === 1 && (await page.locator(".create-locked").count()) === 0);
});

await browser.close();
if (REVIEW) {
  const W = { p390: "390", t768: "768", d1440: "1440" };
  const lines = ["# VideoMK web: the look and cast picker, review set", "", "Taken from the built web app against a mocked API (the capabilities are produced by the server's own code; QA does not serve them yet). 2x pixels.",
    "File name: `<state>__<width>__<light|dark>__<en|es>.jpg` (p390 = 390 px, t768 = 768 px, d1440 = 1440 px). Each state exists in light and dark (English) and in Spanish (light), at the three widths.", ""];
  for (const j of jobs) { lines.push(`## ${j.name}`, j.title, ""); for (const [sz, scheme, loc] of j.combos) lines.push(`- \`${j.name}__${sz}__${scheme}__${loc}.jpg\`: ${W[sz]} px, ${scheme}, ${loc === "es" ? "Spanish" : "English"}`); lines.push(""); }
  fs.writeFileSync(path.join(OUT, "index.md"), lines.join("\n"));
}
console.log(report.join("\n"));
console.log("\n" + checks.join("\n"));
console.log(`\n${report.filter((r) => / ok$/.test(r)).length}/${report.length} shots clean, ${checks.filter((c) => c.startsWith("PASS")).length}/${checks.length} checks pass`);
