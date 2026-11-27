// Counts the words a person can see in the main area of each page (the app shell's rail and tab bar are counted apart), at 1440 and 390 wide, English.
import { chromium } from "playwright-core";
import fs from "fs"; import http from "http"; import path from "path";
const DIST = process.env.DIST, LAND = process.env.LAND;
const server = http.createServer((req, res) => { const u = new URL(req.url, "http://x"); let p = decodeURIComponent(u.pathname); if (p.endsWith("/")) p += "index.html"; else if (!path.extname(p)) p += "/index.html"; const f = path.join(DIST, p); if (!fs.existsSync(f)) { res.writeHead(404); res.end(); return; } res.writeHead(200, { "content-type": ({ ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png" })[path.extname(f)] || "application/octet-stream" }); res.end(fs.readFileSync(f)); }).listen(4456);
const b64 = (o) => Buffer.from(JSON.stringify(o)).toString("base64url");
const tokens = { access_token: "a", id_token: `${b64({ alg: "none" })}.${b64({ sub: "u", email: "maria@example.com", auth_time: Math.floor(Date.now() / 1000) })}.x`, refresh_token: "r", expires_at: Date.now() + 3600e3 * 5 };
const wallet = { balance: 3, unlimited: false, buckets: [{ kind: "daily", remaining: 1, expires_at: null }], next_daily_at: Math.floor(Date.now() / 1000) + 72000 };
const pages = [["watch", "/watch/?id=v2", ".player video"], ["credits", "/wallet/", ".credits-num"], ["settings", "/settings/", ".srow"], ["feedback", "/feedback/", "textarea"], ["signin", "/signin/", ".pbtn"]];
const browser = await chromium.launch({ channel: "chrome" });
for (const [name, url, ready] of pages) for (const w of [1440, 390]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: 900 }, locale: "en-US" });
  if (name !== "signin") await ctx.addInitScript((t) => localStorage.setItem("vmk_auth_tokens", JSON.stringify(t)), tokens);
  await ctx.route(/127\.0\.0\.1:8787/, (r) => { const u = r.request().url(); const j = (b, s = 200) => r.fulfill({ status: s, contentType: "application/json", headers: { "access-control-allow-origin": "*" }, body: JSON.stringify(b) }); if (r.request().method() === "OPTIONS") return r.fulfill({ status: 204, headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*" } }); if (u.includes("/wallet")) return j(wallet); if (u.includes("/watermark")) return j({}, 404); if (/\/videos\/v2/.test(u)) return j({ status: "COMPLETE", title: "How a forest breathes", description: "", url: "/land.mp4" }); return j({}, 404); });
  await ctx.route("**/land.mp4", (r) => r.fulfill({ status: 200, contentType: "video/mp4", body: fs.readFileSync(LAND) }));
  const pg = await ctx.newPage();
  await pg.goto("http://127.0.0.1:4456" + url); await pg.waitForSelector(ready); await pg.waitForTimeout(800);
  const n = await pg.evaluate(() => {
    const vis = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none" && s.opacity !== "0"; };
    const words = (root) => { let n = 0; const walk = (el) => { for (const c of el.childNodes) { if (c.nodeType === 3) { if (c.textContent.trim() && el.closest && vis(el) && !el.closest(".sr-only-vmk,.skip-link,[aria-hidden='true'],script,style,video")) n += c.textContent.trim().split(/\s+/).length; } else if (c.nodeType === 1) walk(c); } }; walk(root); return n; };
    const main = document.querySelector("#content, main, .app-main-bare") || document.body;
    return { main: words(main), chrome: words(document.body) - words(main) };
  });
  console.log(name.padEnd(9), String(w).padStart(5), "main words:", n.main, " shell/other words:", n.chrome);
  await ctx.close();
}
await browser.close(); server.close();
