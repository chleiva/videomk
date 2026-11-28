// Screenshots + behaviour checks of video clips in Create, against a MOCKED API (nothing talks to AWS): node shoot_clips.mjs <outdir> [only-substring]
// Needs the built app on BASE (astro preview, default http://127.0.0.1:4399), playwright-core with Chrome, and ffmpeg clips in CLIPS (land_audio.mp4, port_silent.mp4, big.mp4).
import { chromium } from "/Users/chleiva/code/incident-command-agent/node_modules/playwright-core/index.mjs";
import fs from "fs";
import path from "path";
const OUT = process.argv[2] || "shots", ONLY = process.argv[3] || "";
const BASE = process.env.BASE || "http://127.0.0.1:4399";
const CLIPS = process.env.CLIPS || "/private/tmp/claude-501/-Users-chleiva-code-videomk/d19b0e3e-ca88-5b4b-b8d2-dfc97f1d79f0/scratchpad/vu";
fs.mkdirSync(OUT, { recursive: true });
const b64 = (o) => Buffer.from(JSON.stringify(o)).toString("base64url");
const tokens = { access_token: "a", id_token: `${b64({ alg: "none" })}.${b64({ sub: "user-1" })}.x`, refresh_token: "r", expires_at: Date.now() + 5 * 3600e3 };
const VCAPS = (o = {}) => ({ enabled: true, available: true, paused: false, clips_per_day: 3, clips_left_today: 3, clips_per_video: 2, max_bytes: 25 * 1048576, used_seconds: 5, formats: ["video/mp4", "video/quicktime", "video/webm"], api_url: "https://vid.test/prod", requires_plan: null, ...o });
const caps = (v) => ({
  aspects: [{ id: "16:9", label: "Landscape", ready: true }, { id: "9:16", label: "Vertical", ready: true }],
  resolutions: [{ id: "1080p", label: "1080p", credits_multiplier: 1, aspects: ["16:9", "9:16"] }],
  platforms: [{ id: "other", label: "Just a video", aspect: "16:9", resolution: "1080p", recommended_minutes: 1, max_minutes: null, supports_4k: true }],
  languages: [{ id: "en", label: "English" }], lengths: { min_minutes: 0.25, max_minutes: 12, presets: [0.5, 1, 2] }, max_photos: 100, intake: true, video_upload: v,
});
const SIZES = { d1280: [1280, 860], p390: [390, 844], p320: [320, 640] };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

/** scenario s: { vcaps, slot: "ok"|"quota"|"paused"|"plan"|"dup"|"neterr", analysis: "ready"|"rejected"|"failed"|"hold"|"slow", uploadHold: bool, generate: fn } */
async function setup(ctx, s, log) {
  let n = 0, polls = {};
  s.release = () => {}; const gate = new Promise((r) => (s.release = r));
  await ctx.route(/\.s3\..*amazonaws\.com/, async (r) => {
    if (r.request().method() === "OPTIONS") return r.fulfill({ status: 204, headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "*" } });
    log.push("S3 " + r.request().method() + " bytes=" + (r.request().postDataBuffer()?.length ?? 0));
    if (s.uploadHold) await gate; else await wait(s.uploadMs ?? 150);
    if (s.upNet) return r.abort("failed");
    r.fulfill({ status: 204, headers: { "access-control-allow-origin": "*" } });
  });
  await ctx.route(/vid\.test/, async (route) => {
    const req = route.request(), u = req.url(), m = req.method();
    const H = { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*" };
    const json = (o, st = 200) => route.fulfill({ status: st, contentType: "application/json", headers: H, body: JSON.stringify(o) });
    if (m === "OPTIONS") return route.fulfill({ status: 204, headers: H });
    log.push(`${m} ${u.replace("https://vid.test/prod/users/user-1", "")} ${req.postData() ?? ""}`.slice(0, 220));
    const id = (u.match(/video-uploads\/([^/]+)/) || [])[1];
    if (m === "POST" && u.endsWith("/video-uploads")) {
      if (s.slot === "quota") return json({ code: "video_upload_quota", message: "You have added today's video clips. They come back tomorrow." }, 429);
      if (s.slot === "paused") return json({ code: "video_upload_paused", message: "Adding video clips is paused for a while. Photos still work." }, 503);
      if (s.slot === "plan") return json({ code: "video_upload_plan", message: "Video clips are part of the Pro plan.", requires_plan: "pro" }, 403);
      if (s.slot === "dup") return json({ duplicate: true, clip: { id: "dup1", status: "ready", ready: true, use_audio: false, duration: 5, aspect: 1.78, thumb_url: "https://thumbs.test/1.jpg" } }, 200);
      return json({ id: `clip${++n}`, upload: { url: "https://vid-bucket.s3.eu-west-1.amazonaws.com/", fields: { key: `in/user-1/clip${n}` } }, expires_in: 900, max_bytes: 26214400, used_seconds: 5, clips_left_today: 2 }, 201);
    }
    if (m === "POST" && u.endsWith("/analyse")) return json({ clip: { id, status: "analysing", ready: false } }, 202);
    if (m === "DELETE") return route.fulfill({ status: 204, headers: H });
    if (m === "GET" && id) {
      polls[id] = (polls[id] || 0) + 1;
      if (s.analysis === "hold" || s.analysis === "slow") return json({ clip: { id, status: "analysing", ready: false } });
      if (s.analysis === "rejected") return json({ clip: { id, status: "rejected", ready: false, code: "rejected", message: "We could not use this clip." } });
      if (s.analysis === "failed") return json({ clip: { id, status: "failed", ready: false, code: "check_failed" } });
      if (polls[id] < 2) return json({ clip: { id, status: "analysing", ready: false } });
      const audio = (s.sound ?? true);
      return json({ clip: { id, status: "ready", ready: true, use_audio: audio, width: s.portrait ? 720 : 1280, height: s.portrait ? 1280 : 720, aspect: s.portrait ? 0.5625 : 1.7778, duration: 4, source_duration: 4, trimmed: false, has_audio: audio, audio_used: audio, audio_state: audio ? "speech" : "off", thumb_url: "https://thumbs.test/1.jpg" } });
    }
    if (m === "GET") return json({ clips: [{ id: "r1", status: "ready", ready: true, use_audio: false, duration: 5, aspect: 1.78, thumb_url: "https://thumbs.test/1.jpg" }, { id: "r2", status: "analysing", ready: false }] });
    return json({}, 404);
  });
  await ctx.route(/thumbs\.test/, (r) => r.fulfill({ status: 200, contentType: "image/svg+xml", headers: { "access-control-allow-origin": "*" }, body: `<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"><rect width="320" height="180" fill="#7c5cd6"/><circle cx="160" cy="90" r="40" fill="#f2c94c"/></svg>` }));
  await ctx.route(/backend\.videomk\.com/, async (route) => {
    const req = route.request(), u = req.url(), m = req.method();
    const json = (o, st = 200) => route.fulfill({ status: st, contentType: "application/json", headers: { "access-control-allow-origin": "*" }, body: JSON.stringify(o) });
    if (m === "OPTIONS") return route.fulfill({ status: 204, headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*" } });
    if (u.includes("/capabilities")) return json(caps(s.vcaps ?? VCAPS()));
    if (u.includes("/wallet")) return json({ balance: 12, unlimited: false, buckets: [], next_daily_at: null });
    if (u.includes("/videos/brief")) return json({ status: "ok" });
    if (u.endsWith("/videos/generate")) { log.push("GENERATE " + req.postData()); return json({ video_id: "new1" }); }
    if (/\/videos$/.test(u) && m === "GET") return json({ items: [{ video_id: "v1", title: "x", status: "COMPLETE", created_at: new Date().toISOString(), duration_s: 60 }] });
    return json({}, 404);
  });
}

const OPEN_MENU = [{ click: "button[aria-label='Add photos or a video']" }, { wait: 250 }];
const PICK = (f) => ({ pick: f });
const ADD_CHOICE = (yes) => ({ click: yes ? "label.clip-choice:nth-child(1)" : "label.clip-choice:nth-child(2)" });
const jobs = [];
const J = (name, o) => jobs.push({ name, combos: [["d1280", "light", "en"], ["d1280", "dark", "en"], ["p390", "light", "en"], ["p390", "dark", "en"]], ...o });
J("01_menu", { actions: [...OPEN_MENU] });
J("02_menu_paused", { s: { vcaps: VCAPS({ available: false, paused: true }) }, actions: [...OPEN_MENU], combos: [["d1280", "light", "en"], ["p390", "dark", "en"]] });
J("03_menu_quota", { s: { vcaps: VCAPS({ available: false, clips_left_today: 0 }) }, actions: [...OPEN_MENU], combos: [["d1280", "dark", "en"], ["p320", "light", "en"]] });
J("04_sheet_start", { actions: [PICK("land_audio.mp4"), { wait: 900 }] });
J("05_sheet_ask", { actions: [PICK("land_audio.mp4"), { wait: 700 }, { click: ".clip-actions .btn-primary" }, { wait: 300 }] });
J("06_sheet_yes", { actions: [PICK("land_audio.mp4"), { wait: 700 }, ADD_CHOICE(true), { wait: 300 }] , combos: [["d1280", "light", "en"], ["d1280", "dark", "en"], ["p390", "light", "en"], ["p320", "light", "en"], ["p320", "dark", "en"]] });
J("07_sheet_no_es", { actions: [PICK("port_silent.mp4"), { wait: 700 }, ADD_CHOICE(false), { wait: 300 }], combos: [["d1280", "light", "es"], ["p390", "dark", "es"], ["p320", "light", "es"]] });
J("08_sheet_large", { actions: [PICK("big.mp4"), { wait: 1800 }, ADD_CHOICE(false), { wait: 300 }], combos: [["d1280", "light", "en"], ["p390", "dark", "en"]] });
J("09_sheet_badtype", { actions: [PICK("../garbage.txt"), { wait: 500 }], combos: [["d1280", "light", "en"], ["p390", "dark", "en"]] });
J("10_uploading", { s: { uploadHold: true }, actions: [PICK("land_audio.mp4"), { wait: 700 }, ADD_CHOICE(true), { click: ".clip-actions .btn-primary" }, { wait: 700 }] });
J("11_checking", { s: { analysis: "hold" }, actions: [PICK("land_audio.mp4"), { wait: 700 }, ADD_CHOICE(true), { click: ".clip-actions .btn-primary" }, { wait: 3500 }] });
J("12_ready", { actions: [PICK("land_audio.mp4"), { wait: 700 }, ADD_CHOICE(true), { click: ".clip-actions .btn-primary" }, { wait: 5500 }, { fill: ["#create-text", "My weekend by the lake, relaxed and warm"] }] });
J("13_ready_two", { actions: [PICK("land_audio.mp4"), { wait: 700 }, ADD_CHOICE(true), { click: ".clip-actions .btn-primary" }, { wait: 5000 }, { s: { portrait: true, sound: false } }, PICK("port_silent.mp4"), { wait: 700 }, ADD_CHOICE(false), { click: ".clip-actions .btn-primary" }, { wait: 5500 }, { fill: ["#create-text", "My weekend by the lake, relaxed and warm"] }], combos: [["d1280", "light", "en"], ["d1280", "dark", "en"], ["p390", "light", "en"], ["p320", "dark", "en"]] });
J("14_rejected", { s: { analysis: "rejected" }, actions: [PICK("land_audio.mp4"), { wait: 700 }, ADD_CHOICE(true), { click: ".clip-actions .btn-primary" }, { wait: 5000 }] });
J("15_check_failed", { s: { analysis: "failed" }, actions: [PICK("land_audio.mp4"), { wait: 700 }, ADD_CHOICE(true), { click: ".clip-actions .btn-primary" }, { wait: 5000 }], combos: [["d1280", "light", "en"], ["p390", "dark", "en"]] });
J("16_net_error", { s: { upNet: true }, actions: [PICK("land_audio.mp4"), { wait: 700 }, ADD_CHOICE(true), { click: ".clip-actions .btn-primary" }, { wait: 2500 }], combos: [["d1280", "light", "en"], ["p390", "dark", "en"]] });
J("17_paused_503", { s: { slot: "paused" }, actions: [PICK("land_audio.mp4"), { wait: 700 }, ADD_CHOICE(true), { click: ".clip-actions .btn-primary" }, { wait: 1500 }], combos: [["d1280", "light", "en"], ["p390", "dark", "en"]] });
J("18_quota_429", { s: { slot: "quota" }, actions: [PICK("land_audio.mp4"), { wait: 700 }, ADD_CHOICE(true), { click: ".clip-actions .btn-primary" }, { wait: 1500 }], combos: [["d1280", "dark", "en"], ["p320", "light", "en"]] });
J("19_duplicate", { s: { slot: "dup" }, actions: [PICK("land_audio.mp4"), { wait: 700 }, ADD_CHOICE(false), { click: ".clip-actions .btn-primary" }, { wait: 1500 }], combos: [["d1280", "light", "en"], ["p390", "light", "es"]] });
J("20_recent", { actions: [...OPEN_MENU, { click: "text=Recent clips" }, { wait: 800 }], combos: [["d1280", "light", "en"], ["p390", "dark", "en"]] });
J("22_trim_progress", { actions: [PICK("big.mp4"), { wait: 1800 }, ADD_CHOICE(true), { click: ".clip-actions .btn-primary" }, { wait: 2500 }], combos: [["d1280", "light", "en"], ["p390", "dark", "en"]] });
J("23_trim_ready", { actions: [PICK("big.mp4"), { wait: 1800 }, ADD_CHOICE(true), { click: ".clip-actions .btn-primary" }, { wait: 13000 }], combos: [["d1280", "light", "en"]] });
J("21_ready_es", { actions: [PICK("land_audio.mp4"), { wait: 700 }, ADD_CHOICE(true), { click: ".clip-actions .btn-primary" }, { wait: 5500 }, { fill: ["#create-text", "Mi fin de semana junto al lago, tranquilo y cálido"] }], combos: [["d1280", "light", "es"], ["p390", "dark", "es"]] });

const browser = await chromium.launch({ channel: "chrome" });
const report = [];
for (const j of jobs) {
  if (ONLY && !j.name.includes(ONLY)) continue;
  for (const [sz, scheme, locale] of j.combos) {
    const [w, h] = SIZES[sz];
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme, locale: locale === "es" ? "es-ES" : "en-US", deviceScaleFactor: 1 });
    await ctx.addInitScript(([t, loc]) => { try { localStorage.setItem("vmk_auth_tokens", JSON.stringify(t)); if (loc) localStorage.setItem("vmk_locale", loc); localStorage.setItem("vmk_media_privacy_seen", "1"); } catch {} }, [tokens, locale]);
    const s = { ...(j.s || {}) }, log = [];
    await setup(ctx, s, log);
    const page = await ctx.newPage();
    const errs = [];
    page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errs.push(m.text().slice(0, 200)); });
    page.on("pageerror", (e) => errs.push("pageerror " + String(e).slice(0, 200)));
    try {
      await page.goto(BASE + "/new/", { waitUntil: "networkidle", timeout: 25000 });
      await page.waitForTimeout(800);
      for (const a of j.actions || []) {
        if (a.click) await page.locator(a.click).first().click({ timeout: 6000, force: true });
        if (a.fill) await page.locator(a.fill[0]).first().fill(a.fill[1]);
        if (a.s) Object.assign(s, a.s);
        if (a.pick) { const f = a.pick.startsWith("../") ? "/tmp/vmk-vu-garbage.txt" : path.join(CLIPS, a.pick); if (f.endsWith(".txt")) fs.writeFileSync(f, "hello"); await page.locator("input[type=file][accept*='video/mp4']").first().setInputFiles(f); }
        if (a.wait) await page.waitForTimeout(a.wait);
      }
      const file = path.join(OUT, `${j.name}__${sz}__${scheme}${locale === "es" ? "__es" : ""}.png`);
      await page.screenshot({ path: file, fullPage: false });
      report.push(`${path.basename(file)} ${errs.length ? "ERR " + errs.join(" | ") : "ok"}`);
      if (process.env.LOG) report.push("   " + log.join("\n   "));
    } catch (e) { report.push(`${j.name} ${sz} FAILED ${String(e).slice(0, 250)}`); }
    await ctx.close();
  }
}
await browser.close();
console.log(report.join("\n"));
