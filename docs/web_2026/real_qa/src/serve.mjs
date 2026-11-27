// static server with gzip for text (as CloudFront would compress), for honest Lighthouse numbers: node serve.mjs <dir> <port>
import http from "http"; import fs from "fs"; import path from "path"; import zlib from "zlib";
const [dir, port] = [process.argv[2], Number(process.argv[3])];
const T = { ".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml", ".webp": "image/webp", ".jpg": "image/jpeg", ".png": "image/png", ".mp4": "video/mp4", ".json": "application/json", ".webmanifest": "application/manifest+json", ".woff2": "font/woff2" };
http.createServer((q, s) => {
  let p = path.join(dir, decodeURIComponent(q.url.split("?")[0])); if (!p.startsWith(dir)) return s.writeHead(403).end();
  if (fs.existsSync(p) && fs.statSync(p).isDirectory()) p = path.join(p, "index.html");
  if (!fs.existsSync(p)) return s.writeHead(404).end("not found");
  const ext = path.extname(p), type = T[ext] || "application/octet-stream", st = fs.statSync(p);
  const h = { "Content-Type": type, "Cache-Control": ext === ".html" ? "no-cache" : "public, max-age=31536000, immutable" };
  if (/text|svg|json|javascript/.test(type) && /gzip/.test(q.headers["accept-encoding"] || "")) { s.writeHead(200, { ...h, "Content-Encoding": "gzip" }); return s.end(zlib.gzipSync(fs.readFileSync(p))); }
  const r = q.headers.range && /bytes=(\d+)-(\d*)/.exec(q.headers.range);
  if (r) { const a = Number(r[1]), b = r[2] ? Number(r[2]) : st.size - 1; s.writeHead(206, { ...h, "Content-Range": `bytes ${a}-${b}/${st.size}`, "Content-Length": b - a + 1, "Accept-Ranges": "bytes" }); return fs.createReadStream(p, { start: a, end: b }).pipe(s); }
  s.writeHead(200, { ...h, "Content-Length": st.size, "Accept-Ranges": "bytes" }); fs.createReadStream(p).pipe(s);
}).listen(port, "127.0.0.1");
