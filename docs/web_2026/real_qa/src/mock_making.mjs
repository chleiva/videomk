// The Making banner and the Watch page's making state, with the documented `making` object injected into the REAL list (everything else is the real QA API)
import { open, BASE } from "./lib.mjs";
const [w, theme, lang, variant] = [Number(process.argv[2] || 1440), process.argv[3] || "dark", process.argv[4] || "en", process.argv[5] || "full"];
const { browser, page, log, shot } = await open({ w, h: w < 500 ? 844 : 900, theme, lang, tag: `_${w}_${theme}_${lang}_${variant}` });
let pics = [];
const making = () => variant === "none" ? undefined : variant === "plain" ? { scene_total: 9, scene_done: 2 } : {
  scene_total: 9, scene_done: 4, live_line: lang === "es" ? "Buscando la imagen adecuada" : "Adding footage of sunlit canopies", narration_line: "Sunlight pours through the canopy, and the forest breathes.",
  scenes: Array.from({ length: 9 }, (_, i) => ({ index: i + 1, done: i < 4, ...(i < 4 && i !== 2 && pics[i] ? { thumb_url: pics[i] } : {}) })) };
await page.route(/\/users\/[^/]+\/videos(\?.*)?$/, async (route) => {
  if (route.request().method() !== "GET") return route.continue();
  const res = await route.fetch(); const j = await res.json();
  pics = j.items.filter((x) => x.preview_gif_url).map((x) => x.preview_gif_url);
  j.items.unshift({ video_id: "fake-making", title: "How honey is made", status: "ASSETS_CREATION", created_at: new Date().toISOString(), eta_seconds: 120, making: making() });
  await route.fulfill({ response: res, json: j });
});
await page.route(/\/videos\/fake-making$/, (route) => route.request().method() === "GET" ? route.fulfill({ status: 409, headers: { "access-control-allow-origin": "*" }, json: { message: "Still being made", status: "ASSETS_CREATION", making: making() } }) : route.continue());
await page.goto(BASE + "/generations"); await page.waitForSelector(".mkb"); await page.waitForTimeout(2500); await shot("mk_banner");
await page.goto(BASE + "/watch?id=fake-making"); await page.waitForSelector(".watch-state"); await page.waitForTimeout(2500); await shot("mk_watch");
console.log(log.join("\n") || "clean"); await browser.close();
