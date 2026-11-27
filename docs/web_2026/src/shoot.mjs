import { chromium } from "playwright-core";
import fs from "fs";
const OUT = process.argv[2] || "shots";
const BASE = process.env.BASE || "http://localhost:4399";
const SIZES = { d1440: [1440, 900], l1280: [1280, 800], t820: [820, 1100], p390: [390, 844] };
const b64 = (o) => Buffer.from(JSON.stringify(o)).toString("base64url");
const idToken = `${b64({alg:"none"})}.${b64({sub:"user-1",email:"a@b.c"})}.x`;
const tokens = { access_token: "a", id_token: idToken, refresh_token: "r", expires_at: Date.now() + 3600e3 * 5 };
const caps = {
  aspects: [{id:"16:9",label:"Landscape",ready:true},{id:"9:16",label:"Vertical",ready:true},{id:"1:1",label:"Square",ready:true},{id:"4:5",label:"Portrait",ready:true}],
  resolutions: [{id:"720p",label:"720p",credits_multiplier:1,aspects:["16:9","9:16","1:1","4:5"]},{id:"1080p",label:"1080p",credits_multiplier:1,aspects:["16:9","9:16","1:1","4:5"]},{id:"2160p",label:"4K",credits_multiplier:2,aspects:["16:9"],note:"For YouTube"}],
  platforms: [{id:"youtube",label:"YouTube",aspect:"16:9",resolution:"1080p",recommended_minutes:5,max_minutes:12,supports_4k:true},{id:"tiktok",label:"TikTok",aspect:"9:16",resolution:"1080p",recommended_minutes:0.5,max_minutes:3},{id:"linkedin",label:"LinkedIn",aspect:"1:1",resolution:"1080p",recommended_minutes:1,max_minutes:10},{id:"instagram",label:"Instagram",aspect:"4:5",resolution:"1080p",recommended_minutes:0.5,max_minutes:3}],
  languages: [{id:"en",label:"English"},{id:"es",label:"Español"}],
  lengths: {min_minutes:0.25,max_minutes:12,presets:[0.25,0.5,0.75,1,2,3,5,8,12]}, max_photos: 100, intake: true, deck: {max_mb:50,max_slides:60,formats:["pptx","pdf"]},
};
const now = Date.now();
const iso = (h) => new Date(now - h * 3600e3).toISOString();
const items = [
  {video_id:"v1",title:"How a forest breathes",status:"STARTED_PROCESSING",created_at:iso(0.1),eta_seconds:180},
  {video_id:"v2",title:"Why the sky is blue",status:"COMPLETE",created_at:iso(2),duration_s:91,editable:true,video_url:"/fake.mp4"},
  {video_id:"v3",title:"The history of the printing press",status:"COMPLETE",created_at:iso(5),duration_s:182,editable:true,video_url:"/fake.mp4"},
  {video_id:"v4",title:"Compound interest in 60 seconds",status:"ERROR",created_at:iso(30)},
  {video_id:"v5",title:"What is photosynthesis",status:"COMPLETE",created_at:iso(52),duration_s:60,editable:true,video_url:"/fake.mp4"},
  {video_id:"v6",title:"Mortgage rates explained for first-time buyers in the UK",status:"COMPLETE",created_at:iso(90),duration_s:312,editable:true,video_url:"/fake.mp4"},
];
const wallet = { balance: 3, unlimited: false, buckets: [{kind:"daily",remaining:1,expires_at:Math.floor(now/1000)+3600*5},{kind:"signup",remaining:2,expires_at:null}], next_daily_at: Math.floor(now/1000)+3600*20 };
const fakeMp4 = process.env.MP4;
async function setup(ctx, mode) {
  await ctx.route(/api\.videomk\.com/, async (route) => {
    const u = route.request().url();
    const json = (o, s = 200) => route.fulfill({ status: s, contentType: "application/json", headers: {"access-control-allow-origin":"*"}, body: JSON.stringify(o) });
    if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: {"access-control-allow-origin":"*","access-control-allow-headers":"*","access-control-allow-methods":"*"} });
    if (u.includes("/capabilities")) return json(caps);
    if (u.includes("/wallet")) return json(wallet);
    if (/\/videos\/v\d\/plan/.test(u)) return json({ error: "mock" }, 404);
    if (/\/videos\/(v\d)$/.test(u)) { const id = u.split("/").pop(); return json(items.find((i) => i.video_id === id) || {}); }
    if (u.includes("/videos") && route.request().method() === "GET") return json(mode === "empty" ? { items: [] } : { items });
    return json({}, 404);
  });
  if (fakeMp4) await ctx.route("**/fake.mp4", (r) => r.fulfill({ status: 200, contentType: "video/mp4", body: fs.readFileSync(fakeMp4) }));
}
const jobs = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const browser = await chromium.launch({ channel: "chrome" });
for (const j of jobs) {
  for (const [sz, scheme, locale] of j.combos) {
    const [w, h] = SIZES[sz];
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme, locale: locale === "es" ? "es-ES" : "en-US", deviceScaleFactor: 1 });
    if (j.auth) await ctx.addInitScript((t) => { try { localStorage.setItem("vmk_auth_tokens", JSON.stringify(t)); } catch {} }, tokens);
    await setup(ctx, j.mode);
    const page = await ctx.newPage();
    const errs = [];
    page.on("console", (m) => { if (m.type() === "error") errs.push(m.text().slice(0, 160)); });
    page.on("pageerror", (e) => errs.push("pageerror " + String(e).slice(0, 160)));
    try {
      await page.goto((j.base || BASE) + j.path, { waitUntil: "networkidle", timeout: 20000 });
      await page.waitForTimeout(j.wait || 900);
      for (const a of j.actions || []) {
        if (a.click) await page.locator(a.click).first().click({ timeout: 4000 });
        if (a.fill) await page.locator(a.fill[0]).first().fill(a.fill[1]);
        if (a.wait) await page.waitForTimeout(a.wait);
      }
      const m = await page.evaluate(() => ({ h: document.documentElement.scrollHeight, w: document.documentElement.scrollWidth, text: (document.body.innerText || "").split(/\s+/).filter(Boolean).length, btn: document.querySelectorAll("button,a[href],input,select,textarea").length, url: location.pathname }));
      const f = `${OUT}/${j.name}__${sz}__${scheme}__${locale}.png`;
      await page.screenshot({ path: f, fullPage: j.full !== false });
      console.log(JSON.stringify({ f: f.split("/").pop(), ...m, hscroll: m.w > w + 1, errs: errs.slice(0, 3) }));
    } catch (e) { console.log("FAIL", j.name, sz, scheme, String(e).slice(0, 120)); }
    await ctx.close();
  }
}
await browser.close();
