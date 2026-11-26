// Headless-Chrome check of the login redirect (no credentials needed: it only inspects the
// authorize URL the page navigates to). Usage:
//   node scripts/check-login-redirect.mjs <dist-dir> [--social] [--shots <dir>]
// <dist-dir> must be built with PUBLIC_COGNITO_CLIENT_ID=testclient, and with
// PUBLIC_AUTH_GOOGLE=1 PUBLIC_AUTH_APPLE=1 when --social is given.
import { spawn } from "node:child_process";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";

const dist = path.resolve(process.argv[2] || "dist");
const social = process.argv.includes("--social");
const shotsAt = process.argv.indexOf("--shots");
const shots = shotsAt > 0 ? process.argv[shotsAt + 1] : null;
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const AUTH_HOST = "auth.videomk.com";
const PORT = 4321;
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml" };

const server = http.createServer((req, res) => {
  let p = path.join(dist, decodeURIComponent(new URL(req.url, "http://x").pathname));
  if (fs.existsSync(p) && fs.statSync(p).isDirectory()) p = path.join(p, "index.html");
  if (!fs.existsSync(p)) { res.writeHead(404).end("nf"); return; }
  res.writeHead(200, { "content-type": types[path.extname(p)] || "application/octet-stream" }).end(fs.readFileSync(p));
}).listen(PORT);

const chrome = spawn(CHROME, ["--headless=new", "--remote-debugging-port=9333", "--user-data-dir=" + fs.mkdtempSync("/tmp/chk-"), "--no-first-run", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let failures = 0;
const ok = (c, m) => { console.log((c ? "PASS " : "FAIL ") + m); if (!c) failures++; };

async function connect() {
  for (let i = 0; i < 50; i++) {
    try {
      const list = await (await fetch("http://127.0.0.1:9333/json")).json();
      const t = list.find((x) => x.type === "page");
      if (t) return t.webSocketDebuggerUrl;
    } catch {}
    await sleep(200);
  }
  throw new Error("chrome did not start");
}
const ws = new WebSocket(await connect());
await new Promise((r) => (ws.onopen = r));
let id = 0; const waits = new Map(); const handlers = [];
ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && waits.has(d.id)) { waits.get(d.id)(d); waits.delete(d.id); } else handlers.forEach((h) => h(d)); };
const send = (method, params = {}) => new Promise((r) => { const i = ++id; waits.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async (expr) => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value;

let authUrls = [];
handlers.push(async (d) => {
  if (d.method === "Fetch.requestPaused") {
    const u = d.params.request.url;
    if (u.includes(AUTH_HOST)) { if (u.includes("/oauth2/authorize")) authUrls.push(u); await send("Fetch.fulfillRequest", { requestId: d.params.requestId, responseCode: 200, body: Buffer.from("auth").toString("base64") }); }
    else await send("Fetch.continueRequest", { requestId: d.params.requestId });
  }
});
await send("Page.enable"); await send("Runtime.enable");
await send("Fetch.enable", { patterns: [{ urlPattern: "*" }] });
const go = async (url) => { await send("Page.navigate", { url }); await sleep(1200); };
const param = (u, k) => new URL(u).searchParams.get(k);
const home = () => go(`http://localhost:${PORT}/support/index.html`); // a same-origin page without auth redirect
const last = () => authUrls[authUrls.length - 1];

// 1. Protected page, signed out: today's behaviour (direct) or the chooser (social on).
await home();
await ev("localStorage.clear(); sessionStorage.clear()");
authUrls = [];
await go(`http://localhost:${PORT}/generations/index.html`);
if (!social) {
  ok(authUrls.length === 1, "signed-out protected page goes straight to the hosted UI");
  ok(!!last() && !last().includes("identity_provider"), "no identity_provider when switches are off");
  ok(param(last(), "code_challenge_method") === "S256" && !!param(last(), "state"), "PKCE S256 and state present");
  ok(!(await ev("document.body.innerText")).includes("Continue with Google"), "no social buttons rendered");
} else {
  ok(authUrls.length === 0 && (await ev("location.pathname")).startsWith("/signin"), "signed-out protected page shows the chooser");
  const labels = await ev("[...document.querySelectorAll('button[data-provider]')].map(b=>b.getAttribute('aria-label')).join('|')");
  ok(labels === "Continue with Google|Continue with Apple|Continue with email", "three options rendered: " + labels);
  if (shots) {
    fs.mkdirSync(shots, { recursive: true });
    for (const [name, w, h, scheme] of [["light", 900, 700, "light"], ["dark", 900, 700, "dark"], ["360-light", 360, 740, "light"], ["360-dark", 360, 740, "dark"]]) {
      await send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 2, mobile: w < 500 });
      await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: scheme }] });
      await sleep(300);
      const s = await send("Page.captureScreenshot", { format: "png" });
      fs.writeFileSync(path.join(shots, `signin-${name}.png`), Buffer.from(s.result.data, "base64"));
    }
    // focus ring on the first button
    await send("Emulation.setDeviceMetricsOverride", { width: 360, height: 740, deviceScaleFactor: 2, mobile: true });
    await ev("document.querySelector('button[data-provider]').focus()");
    await send("Input.dispatchKeyEvent", { type: "keyDown", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 });
    await send("Input.dispatchKeyEvent", { type: "keyUp", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 });
    const s = await send("Page.captureScreenshot", { format: "png" });
    fs.writeFileSync(path.join(shots, "signin-360-focus.png"), Buffer.from(s.result.data, "base64"));
    await send("Emulation.clearDeviceMetricsOverride");
  }
  for (const [sel, want] of [["google", "Google"], ["apple", "SignInWithApple"], ["email", null]]) {
    await go(`http://localhost:${PORT}/signin/index.html`);
    authUrls = [];
    await ev(`document.querySelector('button[data-provider=${sel}]').click()`);
    await sleep(800);
    const u = last();
    ok(!!u && u.startsWith(`https://${AUTH_HOST}/oauth2/authorize?`), `${sel}: navigates to authorize`);
    ok(u && param(u, "identity_provider") === want, `${sel}: identity_provider=${want}`);
    ok(u && param(u, "code_challenge_method") === "S256" && (param(u, "state") || "").length >= 20, `${sel}: PKCE S256 and a random state`);
  }
}
// 2. Callback error handling (works in both modes).
await home();
await ev("localStorage.setItem('vmk_auth_state','abc'); localStorage.setItem('vmk_auth_provider','Google'); localStorage.setItem('vmk_pkce_verifier','v')");
authUrls = [];
await go(`http://localhost:${PORT}/auth/callback/index.html?error=invalid_request&error_description=Already%20found%20an%20entry%20for%20username%20Google_1&state=abc`);
const retryUrl = authUrls[0];
ok(!!retryUrl && param(retryUrl, "identity_provider") === "Google", "link-race error retries once with the same provider");
ok(!!retryUrl && param(retryUrl, "state") !== "abc", "retry uses a fresh state");
await home();
await ev("localStorage.setItem('vmk_auth_state','abc2')");
authUrls = [];
await go(`http://localhost:${PORT}/auth/callback/index.html?error=invalid_request&error_description=Already%20found%20an%20entry%20for%20username%20Google_1&state=abc2`);
ok(authUrls.length === 0, "second link-race error does not loop");
ok((await ev("document.getElementById('msg').textContent")).includes("try signing in again"), "clear error shown after retry used");
await ev("localStorage.setItem('vmk_auth_state','abc3')");
await go(`http://localhost:${PORT}/auth/callback/index.html?error=server_error&error_description=%3Cimg%20src%3Dx%20onerror%3Dalert(1)%3E&state=abc3`);
ok((await ev("document.querySelectorAll('#msg img').length")) === 0, "error_description is not rendered as HTML");
authUrls = [];
await ev("sessionStorage.clear(); localStorage.setItem('vmk_auth_state','real')");
await go(`http://localhost:${PORT}/auth/callback/index.html?error=invalid_request&error_description=Already%20found%20an%20entry%20for%20username%20x&state=forged`);
ok(authUrls.length === 0, "mismatched state never triggers a retry");

ws.close(); chrome.kill(); server.close();
console.log(failures ? `${failures} FAILED` : "all passed");
process.exit(failures ? 1 : 0);
