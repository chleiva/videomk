// Watch, Settings, Credits and the failed-video actions against the real QA API
import { open, BASE, S } from "./lib.mjs";
const VID = "c34f867a-eb2c-50d7-b772-7ce773468b02", PROMPT = "How bees make honey, and why forests matter to them. Calm and warm, using my photos.";
const { browser, ctx, page, log, shot } = await open({ tag: "_real" });
await ctx.addInitScript(([id, p]) => { try { if (!localStorage.getItem("vmk_prompts")) localStorage.setItem("vmk_prompts", JSON.stringify([[id, p]])); } catch {} }, [VID, PROMPT]);
const step = (s) => console.log("STEP", s);
const calls = []; page.on("response", (r) => { const u = r.url(); if (/execute-api/.test(u) && !["GET", "OPTIONS"].includes(r.request().method())) calls.push(`${r.status()} ${r.request().method()} ${u.split("?")[0].replace(/users\/[^/]+/, "users/U").replace(/^https:\/\/[^/]+\/prod/, "")}`); });
await page.goto(BASE + "/generations"); await page.waitForSelector(".vtile-link");
await page.locator(`.vtile-link[href*="${VID}"]`).click(); await page.waitForURL(/watch/); await page.waitForSelector("video", { timeout: 20000 });
await page.waitForFunction(() => document.querySelector("video")?.readyState >= 1, null, { timeout: 30000 }).catch(() => log.push("FLOW: video metadata never loaded"));
step("title: " + (await page.locator(".watch-title").innerText()) + " | meta: " + (await page.locator(".watch-meta").innerText().catch(() => "")));
step("prompt column: " + (await page.locator(".watch-prompt").innerText().catch(() => "(absent)")).replace(/\n/g, " | "));
await page.locator(".player-big").click(); await page.waitForTimeout(3500);
const st = await page.evaluate(() => { const v = document.querySelector("video"); return { t: v.currentTime, paused: v.paused, w: v.videoWidth, h: v.videoHeight, d: v.duration }; });
step("playing: " + JSON.stringify(st)); await shot("w2_playing");
await page.keyboard.press("k"); await page.waitForTimeout(300); step("k pauses: " + (await page.evaluate(() => document.querySelector("video").paused)));
await page.evaluate(() => { try { Object.defineProperty(navigator, "share", { value: undefined, configurable: true }); } catch {} });   // no share sheet in a headless browser: take the copy-link path
await page.getByRole("button", { name: "Share" }).click(); await page.waitForTimeout(600);
step("share toast: " + (await page.locator(".toast").innerText().catch(() => "(none)")) + " | clipboard is a link: " + /^https:\/\//.test(await page.evaluate(() => navigator.clipboard.readText()).catch(() => "")));
const dl = page.waitForEvent("download", { timeout: 20000 }).then((d) => "download " + d.suggestedFilename()).catch(() => "no download event");
await page.getByRole("button", { name: "Save" }).click(); step("save: " + (await dl) + " | still on watch: " + /watch/.test(page.url()));
await page.getByRole("button", { name: "More" }).click(); await page.waitForTimeout(300); await shot("w3_more");
step("more menu: " + (await page.locator('.menu [role="menuitem"]').allInnerTexts()).join(", "));
await page.locator('.menu [role="menuitem"]').first().click(); await page.waitForTimeout(500); await shot("w4_details");
step("details sheet: " + (await page.locator('[role="dialog"]').innerText().catch(() => "(none)")).slice(0, 160).replace(/\n/g, " | ")); await page.keyboard.press("Escape");
step("chips: " + JSON.stringify(await page.locator(".watch-chips a").evaluateAll((a) => a.map((x) => [x.textContent, decodeURIComponent(x.getAttribute("href")).slice(0, 90)]))));
await page.locator(".watch-chips a").first().click(); await page.waitForURL(/\/new/); await page.waitForSelector("#create-text"); await page.waitForTimeout(1500);
step("Make it a Short opens Create: text=" + JSON.stringify((await page.locator("#create-text").inputValue()).slice(0, 50)) + " pills=" + (await page.locator(".composer-pills .pill").allInnerTexts()).map((x) => x.replace(/\n/g, " ")).join(" / ") + " cost=" + (await page.locator(".go-cost").innerText())); await shot("w5_short");
await page.goto(BASE + `/watch?id=${VID}`); await page.waitForSelector("video");
if (await page.locator('a[aria-label="Edit"]').count()) { await page.locator('a[aria-label="Edit"]').click(); await page.waitForURL(/edit/); await page.waitForLoadState("networkidle").catch(() => {}); await page.waitForTimeout(2500); await shot("w6_editor"); step("editor: " + (await page.locator("main").innerText()).slice(0, 200).replace(/\n/g, " | ")); } else step("no Edit action (not editable)");
// credits
await page.goto(BASE + "/wallet"); await page.waitForLoadState("networkidle").catch(() => {}); await page.waitForTimeout(1200); await shot("w7_wallet"); step("credits page: " + (await page.locator("main").innerText()).slice(0, 260).replace(/\n/g, " | "));
// settings: language, appearance, a preference, watermark default
await page.goto(BASE + "/settings"); await page.waitForLoadState("networkidle").catch(() => {}); await page.waitForTimeout(800);
await page.getByRole("radio", { name: "Español" }).or(page.getByRole("button", { name: "Español" })).first().click(); await page.waitForTimeout(600);
step("Spanish: h1=" + (await page.locator("main h1.h1, main h1").first().innerText()) + " nav=" + (await page.locator(".app-rail a, .app-nav a").allInnerTexts()).slice(0, 4).join(",").replace(/\n/g, " "));
await page.getByRole("radio", { name: "English" }).or(page.getByRole("button", { name: "English" })).first().click(); await page.waitForTimeout(400);
await page.getByRole("radio", { name: "Dark" }).or(page.getByRole("button", { name: "Dark" })).first().click(); await page.waitForTimeout(400);
step("dark: data-theme=" + (await page.evaluate(() => document.documentElement.dataset.theme)) + " bg=" + (await page.evaluate(() => getComputedStyle(document.body).backgroundColor))); await shot("w8_settings_dark");
await page.getByRole("radio", { name: "Light" }).or(page.getByRole("button", { name: "Light" })).first().click();
await page.getByRole("radio", { name: "videomk" }).or(page.getByRole("button", { name: "videomk", exact: true })).first().click(); await page.waitForTimeout(1500);
await shot("w9_watermark"); 
await page.getByRole("radio", { name: "None" }).or(page.getByRole("button", { name: "None" })).first().click(); await page.waitForTimeout(1500);
step("settings writes: " + calls.join(" ; "));
// failed video: the card with Try again and Remove (the item is injected: this account has no failed video; the two calls go to the real API)
calls.length = 0;
await page.route(/\/users\/[^/]+\/videos(\?.*)?$/, async (route) => { if (route.request().method() !== "GET") return route.continue(); const res = await route.fetch(); const j = await res.json(); if (!globalThis.__gone) j.items.unshift({ video_id: "00000000-0000-4000-8000-00000000dead", title: "A video that did not finish", status: "FAILED", created_at: new Date().toISOString(), can_retry: true }); await route.fulfill({ response: res, json: j }); });
await page.goto(BASE + "/generations"); await page.waitForSelector(".vtile.is-failed"); await shot("w10_failed");
step("failed card: " + (await page.locator(".vtile.is-failed").innerText()).replace(/\n/g, " | "));
await page.locator(".vtile.is-failed").getByRole("button", { name: "Try again" }).click(); await page.waitForTimeout(2500);
step("try again -> toast: " + (await page.locator(".toast").innerText().catch(() => "(none)")) + " | " + calls.join(" ; ")); calls.length = 0;
globalThis.__gone = true;
await page.locator(".vtile.is-failed").getByRole("button", { name: "Remove" }).click(); await page.waitForTimeout(2500);
step("remove -> toast: " + (await page.locator(".toast").innerText().catch(() => "(none)")) + " | card left: " + (await page.locator(".vtile.is-failed").count()) + " | " + calls.join(" ; "));
console.log("LOG\n" + [...new Set(log)].join("\n")); await browser.close();
