// My media against the real QA API: upload, grid, search, viewer, collection, select
import { open, BASE, S } from "./lib.mjs";
const { browser, page, log, shot } = await open({ tag: "_real" });
const api = [];
page.on("response", async (r) => { const u = r.url(); if (/execute-api|s3[.-]/.test(u) && !/thumb|\.jpg\?|\.gif|\.mp4/.test(u) && r.request().method() !== "OPTIONS") { let b = ""; try { if (/execute-api/.test(u)) b = (await r.text()).slice(0, 260).replace(/https:\/\/[^"]{50,}/g, "<url>"); } catch {} api.push(`${r.status()} ${r.request().method()} ${u.split("?")[0].replace(/users\/[^/]+/, "users/U").replace(/^https:\/\/[^/]+(\/prod)?/, "").slice(0, 90)}${u.includes("?") && /execute-api/.test(u) ? "?" + u.split("?")[1].slice(0, 60) : ""} ${b}`); } });
await page.goto(BASE + "/media"); await page.waitForLoadState("networkidle");
const got = page.getByRole("button", { name: "Got it" }); if (await got.count()) await got.click();
// start clean: delete what an earlier run left (this exercises select + delete + confirm against the real API)
if (await page.locator(".mtile").count()) {
  await page.getByRole("button", { name: "Select", exact: true }).click();
  const n = await page.locator(".mtile-btn").count(); for (let i = 0; i < n; i++) await page.locator(".mtile-btn").nth(i).click();
  await page.locator(".selbar-del").click(); await page.waitForTimeout(400); await shot("m0_delete_confirm");
  await page.getByRole("dialog").getByRole("button", { name: "Delete" }).click();
  await page.waitForFunction(() => document.querySelectorAll(".mtile").length === 0, null, { timeout: 20000 }).catch(() => log.push("FLOW: delete did not empty the grid"));
  console.log("deleted", n, "-> tiles now", await page.locator(".mtile").count());
}
const t0 = Date.now();
const files = ["forest1.jpg", "forest2.jpg", "bees1.jpg", "bees2.jpg"].map((f) => `${S}/photos/${f}`);
await page.locator('.mpage input[type="file"]').setInputFiles(files);
await page.waitForSelector(".upload-banner", { timeout: 10000 }); await page.waitForTimeout(700); await shot("m1_uploading");
await page.waitForFunction(() => document.querySelectorAll(".mtile img").length >= 4, null, { timeout: 90000 }).then(() => console.log("4 tiles after", Math.round((Date.now() - t0) / 100) / 10, "s")).catch(() => log.push("FLOW: 4 tiles did not appear within 90 s"));
await page.waitForTimeout(2500); await shot("m2_uploaded");
console.log("tiles:", await page.locator(".mtile").count(), "| banner:", (await page.locator(".upload-banner").innerText().catch(() => "(gone)")).replace(/\n/g, " | "));
console.log("heads:", await page.locator(".mhead").allInnerTexts());
// search by meaning
await page.locator(".msearch input").fill("bee on a flower"); await page.waitForTimeout(4000); await shot("m3_search");
console.log("search 'bee on a flower' tiles:", await page.locator(".mtile").count(), "chips:", await page.locator(".mchips .chip").allInnerTexts());
await page.locator(".msearch input").fill(""); await page.waitForTimeout(2500);
console.log("after delete, select mode off:", (await page.getByRole("button", { name: "Select", exact: true }).count()) === 1, "| upload card auto-dismissed:", (await page.locator(".upload-banner").count()) === 0);
// viewer
await page.locator(".mtile-btn").first().click(); await page.waitForTimeout(1500); await shot("m4_viewer");
console.log("viewer open:", await page.locator('[role="dialog"]').count()); await page.keyboard.press("Escape"); await page.waitForTimeout(400);
// select mode
await page.getByRole("button", { name: "Select", exact: true }).click();
for (let i = 0; i < 3; i++) await page.locator(".mtile-btn").nth(i).click();
await page.waitForTimeout(500); await shot("m5_selected");
console.log("selbar:", (await page.locator(".selbar").innerText()).replace(/\n/g, " | "));
console.log("LOG\n" + [...new Set(log)].join("\n")); console.log("API\n" + api.join("\n"));
await browser.close();
