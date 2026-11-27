// The whole journey against the real QA API: My media -> select -> "Make a video · 3" -> Create (15 s, 1 credit) -> Making -> Watch
import fs from "fs"; import { open, BASE, S } from "./lib.mjs";
const { browser, page, log, shot } = await open({ tag: "_real" });
const seen = [], posts = [];
page.on("request", (r) => { if (/videos\/(generate|brief)$/.test(r.url()) && r.method() === "POST") posts.push({ url: r.url().split("/").pop(), body: r.postData() }); });
page.on("response", async (r) => { const u = r.url(); if (!/execute-api/.test(u) || r.request().method() === "OPTIONS") return;
  if (/videos\/(generate|brief)$/.test(u)) { let b = ""; try { b = (await r.text()).slice(0, 500); } catch {} console.log("  <-", r.status(), u.split("/").pop(), b); }
  if (/\/videos$/.test(u.split("?")[0]) && r.request().method() === "GET") { try { const j = await r.json(); const m = j.items.find((x) => !["COMPLETE", "FAILED", "ERROR", "REJECTED", "CANCELLED"].includes(x.status)); if (m) seen.push({ t: new Date().toISOString().slice(11, 19), status: m.status, stage: m.stage, eta: m.eta_seconds, making: m.making ? { ...m.making, scenes: (m.making.scenes || []).map((s) => ({ ...s, thumb_url: s.thumb_url ? "<signed>" : undefined })) } : undefined }); } catch {} } });
const step = (s) => console.log("STEP", s);
await page.goto(BASE + "/media"); await page.waitForSelector(".mtile img", { timeout: 30000 });
await page.getByRole("button", { name: "Select", exact: true }).click();
for (let i = 0; i < 3; i++) await page.locator(".mtile-btn").nth(i).click();
await page.locator(".selbar-go").click(); await page.waitForURL(/\/new/); await page.waitForSelector(".attach-strip"); await page.waitForTimeout(1500);
step("composer opened with photos: " + (await page.locator(".attach").count()) + " | " + (await page.locator(".attach-count").innerText()));
// back keeps the selection
await page.goBack(); await page.waitForSelector(".selbar"); step("back to media keeps selection: " + (await page.locator(".selbar-n").innerText()));
await page.locator(".selbar-go").click(); await page.waitForURL(/\/new/); await page.waitForSelector(".attach-strip");
await page.locator("#create-text").fill("How bees make honey, and why forests matter to them. Calm and warm, using my photos.");
await page.getByRole("button", { name: "Length" }).click(); await shot("c1_length_menu");
await page.getByRole("menuitemradio", { name: /^15 s/ }).click();
await page.waitForTimeout(400); await shot("c2_ready");
const cta = await page.locator(".compose-go").innerText(); step("Create button: " + cta.replace(/\n/g, " "));
if (!/1\s*$/.test(cta.trim())) { console.log("ABORT: cost is not 1 credit"); await browser.close(); process.exit(1); }
await page.locator(".compose-go").click();
await page.waitForSelector(".compose-progress", { timeout: 5000 }).then(() => step("wait capsule: " + "shown")).catch(() => step("wait capsule: not seen"));
await shot("c3_checking");
step("capsule text: " + (await page.locator(".compose-progress").innerText().catch(() => "")).replace(/\n/g, " | ") + " | form inert: " + (await page.locator(".composer-card").getAttribute("inert").catch(() => null)));
const out = await Promise.race([page.waitForURL(/generations/, { timeout: 90000 }).then(() => "started"), page.waitForSelector('[role="dialog"]', { timeout: 90000 }).then(() => "sheet")]).catch(() => "timeout");
step("after Create: " + out);
if (out === "sheet") { await shot("c4_sheet"); console.log("sheet:", (await page.locator('[role="dialog"]').innerText()).slice(0, 400)); const now = page.getByRole("button", { name: /Make it now/i }); if (await now.count()) { await now.click(); await page.waitForURL(/generations/, { timeout: 90000 }); } else { console.log("LOG", log.join("\n")); await browser.close(); process.exit(1); } }
if (out === "timeout") { await shot("c4_timeout"); console.log("hint:", await page.locator(".compose-notes").innerText().catch(() => "")); console.log("LOG", log.join("\n")); await browser.close(); process.exit(1); }
console.log("POSTS", JSON.stringify(posts.map((p) => ({ url: p.url, body: JSON.parse(p.body || "{}") })), null, 1).slice(0, 1500));
await page.waitForSelector(".mkb", { timeout: 20000 }).catch(() => log.push("FLOW: no making banner after Create"));
await page.waitForTimeout(800); await shot("k00_banner"); step("toast: " + (await page.locator(".toast").innerText().catch(() => "(none)")) + " | url " + page.url());
const t0 = Date.now(); let i = 0, lastLine = "";
while (Date.now() - t0 < 20 * 60000) {
  if (!(await page.locator(".mkb").count())) break;
  const line = (await page.locator(".mkb").innerText().catch(() => "")).replace(/\n/g, " | ");
  if (line !== lastLine) { lastLine = line; i++; console.log(`  [${Math.round((Date.now() - t0) / 1000)}s] ${line} | tiles ${await page.locator(".mkb .strip-tile").count()} done ${await page.locator(".mkb .strip-tile.is-done").count()} pics ${await page.locator(".mkb .strip-tile img").count()}`); await shot("k" + String(i).padStart(2, "0") + "_banner"); }
  await page.waitForTimeout(3000);
}
step(`banner gone after ${Math.round((Date.now() - t0) / 1000)} s`);
fs.writeFileSync(S + "/pw/making_seen.json", JSON.stringify(seen, null, 1));
await page.waitForTimeout(1500); await shot("k99_done");
const first = page.locator(".vtile").first(); step("first tile: " + (await first.innerText()).replace(/\n/g, " | "));
console.log("LOG\n" + [...new Set(log)].join("\n"));
await browser.close();
