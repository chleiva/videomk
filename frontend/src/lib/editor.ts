// Editor model: types, API calls, and the pure functions that turn "what the user wants the video to be" into the
// operations the server validates and applies. The UI edits a LOCAL WORKING COPY; submit = diff(server, local).
import { getAuthorizationHeader } from "./auth";
import { apiGateway } from "./config";
import { currentLocaleHeaders, t, translate } from "./i18n";
import type { Locale } from "./i18n";

export type SceneType = "title" | "bullets" | "diagram" | "chart" | "timeline" | "stat" | "quote" | "image";
export const SCENE_TYPES: SceneType[] = ["title", "bullets", "diagram", "chart", "timeline", "stat", "quote", "image"];

export interface Candidate {
  provider: string;
  id: string;
  thumb_url: string;
  creator: string;
  license: string;
  alt?: string;
  width: number;
  height: number;
}

export interface Beat {
  id: string;
  narration: string;
  scene: { type: SceneType; props: Record<string, any> };
  chapter?: string | null;
  pick?: string | null;
  duration?: number | null;
  stale?: boolean;
  photo?: { url: string | null; credit?: string | null; chosen?: string | null; no_photo?: boolean };
  candidates?: Candidate[];
  ref?: string; // present on beats that exist only locally (not yet saved)
}

export interface Meta {
  title: string;
  theme: string;
  mood: string;
  voice: string;
}

export interface PlanView {
  video_id: string;
  rev: number;
  status: string;
  edit_state: "READY" | "RENDERING" | "FAILED";
  edit_mode?: string;
  edit_error?: string;
  title: string;
  description: string;
  theme: string;
  mood: string;
  voice: string;
  beats: Beat[];
  final: { url: string | null; rev?: number | null };
  preview: { url: string | null; rev?: number | null };
  limits: { max_beats: number; min_words: number; max_words: number };
  scene_types: SceneType[];
}

export type Op = Record<string, any>;

export class ApiError extends Error {
  constructor(public status: number, message: string, public rev?: number) {
    super(message);
  }
}

async function call(method: "GET" | "POST", url: (userId: string) => string, body?: unknown): Promise<any> {
  const { Authorization, userId } = await getAuthorizationHeader();
  if (!userId) throw new ApiError(401, t("api.signed_in_required"));
  const res = await fetch(url(userId), {
    method,
    headers: { Authorization, ...currentLocaleHeaders(), ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  let data: any = {};
  try {
    data = await res.json();
  } catch {}
  if (!res.ok) throw new ApiError(res.status, data.message || t("api.request_failed", { status: res.status }), data.rev);
  return data;
}

export const getPlan = (videoId: string): Promise<PlanView> => call("GET", (u) => apiGateway.plan(u, videoId));
export const postEdits = (videoId: string, body: { base_rev: number; ops: Op[]; mode: "preview" | "final" }) =>
  call("POST", (u) => apiGateway.edits(u, videoId), body);

// ------------------------------------------------------------------ helpers
export function stable(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(stable).join(",")}]`;
  if (v && typeof v === "object") {
    const o = v as Record<string, unknown>;
    return `{${Object.keys(o).sort().map((k) => `${JSON.stringify(k)}:${stable(o[k])}`).join(",")}}`;
  }
  return JSON.stringify(v);
}

export const wordCount = (s: string) => (s.trim() ? s.trim().split(/\s+/).length : 0);

export function emptyScene(type: SceneType, narration = ""): Beat["scene"] {
  const first = narration.trim().split(/\s+/).slice(0, 6).join(" ");
  switch (type) {
    case "title": return { type, props: { title: first, subtitle: "" } };
    case "bullets": return { type, props: { heading: "", items: ["", ""] } };
    case "diagram": return { type, props: { title: "", nodes: [], edges: [] } };
    case "chart": return { type, props: { kind: "bar", title: "", labels: [], values: [], unit: "" } };
    case "timeline": return { type, props: { title: "", events: [] } };
    case "stat": return { type, props: { value: "", label: "" } };
    case "quote": return { type, props: { text: "", attribution: "" } };
    case "image": return { type, props: { image_query: "", alt: "" } };
  }
}

/** Mirrors the server's rules so problems show up next to the field, before anything is sent. */
export function validateBeat(b: Beat, limits: { min_words: number; max_words: number }, locale: Locale = "en"): string[] {
  const errs: string[] = [];
  const tr = (key: string, params?: Record<string, string | number>) => translate(key, locale, params);
  const n = wordCount(b.narration);
  if (n < limits.min_words) errs.push(tr("val.narr_min", { min: limits.min_words }));
  if (n > limits.max_words) errs.push(tr("val.narr_max", { max: limits.max_words }));
  const p = b.scene.props;
  const filled = (a: any) => (Array.isArray(a) ? a.filter((x) => String(x).trim()).length : 0);
  switch (b.scene.type) {
    case "title": if (!String(p.title || "").trim()) errs.push(tr("val.title")); break;
    case "bullets": if (filled(p.items) < 2) errs.push(tr("val.bullets")); break;
    case "diagram": if ((p.nodes || []).length < 2) errs.push(tr("val.diagram")); break;
    case "chart": if ((p.labels || []).length < 2 || (p.values || []).length < 2) errs.push(tr("val.chart")); break;
    case "timeline": if ((p.events || []).length < 2) errs.push(tr("val.timeline")); break;
    case "stat": if (!String(p.value || "").trim()) errs.push(tr("val.stat")); break;
    case "quote": if (!String(p.text || "").trim()) errs.push(tr("val.quote")); break;
    case "image": if (!String(p.image_query || "").trim()) errs.push(tr("val.image")); break;
  }
  return errs;
}

// ------------------------------------------------------------------ diff -> ops
export function diffOps(server: Beat[], local: Beat[], serverMeta: Meta, localMeta: Meta): Op[] {
  const ops: Op[] = [];
  const meta: Op = {};
  if (localMeta.title !== serverMeta.title) meta.title = localMeta.title;
  if (localMeta.theme !== serverMeta.theme) meta.theme = localMeta.theme;
  if (localMeta.mood !== serverMeta.mood) meta.mood = localMeta.mood;
  if (Object.keys(meta).length) ops.push({ op: "set_meta", ...meta });
  if (localMeta.voice !== serverMeta.voice) ops.push({ op: "set_voice", voice: localMeta.voice });

  const handle = (b: Beat) => (b.ref ? `ref:${b.ref}` : b.id);
  const keep = new Set(local.filter((b) => !b.ref).map((b) => b.id));

  for (const s of server) if (!keep.has(s.id)) ops.push({ op: "delete", id: s.id });

  // inserts, placed after whatever precedes them locally (a real id, or the ref of an earlier insert)
  local.forEach((b, i) => {
    if (!b.ref) return;
    const prev = i > 0 ? handle(local[i - 1]) : null;
    ops.push({ op: "insert", ref: b.ref, after: prev, narration: b.narration, scene: b.scene, ...(b.chapter ? { chapter: b.chapter } : {}) });
  });

  const byId = new Map(server.map((b) => [b.id, b]));
  for (const b of local) {
    const s = !b.ref ? byId.get(b.id) : undefined;
    if (!s) continue;
    if (b.narration !== s.narration) ops.push({ op: "set_narration", id: b.id, text: b.narration });
    const sceneChanged = stable(b.scene) !== stable(s.scene);
    if (sceneChanged) ops.push({ op: "set_scene", id: b.id, type: b.scene.type, props: b.scene.props });
    if (b.scene.type === "image" && b.pick && b.pick !== (s.pick ?? null) && (!sceneChanged || b.scene.props.image_query === s.scene.props.image_query)) {
      ops.push({ op: "pick_image", id: b.id, candidate: b.pick });
    }
    if ((b.chapter || "") !== (s.chapter || "")) ops.push({ op: "set_chapter", id: b.id, title: b.chapter || "" });
  }

  // order: simulate the server's list after deletes+inserts, then move beats into place one by one
  const cur: string[] = server.filter((s) => keep.has(s.id)).map((s) => s.id);
  local.forEach((b, i) => {
    if (!b.ref) return;
    const after = i > 0 ? handle(local[i - 1]) : null;
    const at = after === null ? 0 : cur.indexOf(after) + 1;
    cur.splice(at, 0, `ref:${b.ref}`);
  });
  const want = local.map(handle);
  for (let i = 0; i < want.length; i++) {
    if (cur[i] !== want[i]) {
      cur.splice(cur.indexOf(want[i]), 1);
      cur.splice(i, 0, want[i]);
      ops.push({ op: "move", id: want[i], to: i });
    }
  }
  return ops;
}

// ------------------------------------------------------------------ text formats for the structured scenes
const lines = (t: string) => t.split("\n").map((l) => l.trim()).filter(Boolean);

export const bulletsToText = (items: string[] = []) => items.join("\n");
export const textToBullets = (t: string) => lines(t).slice(0, 5);

export function diagramToText(props: Record<string, any>): string {
  const label = new Map<string, string>((props.nodes || []).map((n: any) => [String(n.id), String(n.label ?? n.id)]));
  const used = new Set<string>();
  const out: string[] = [];
  for (const e of props.edges || []) {
    used.add(String(e[0])); used.add(String(e[1]));
    out.push(`${label.get(String(e[0])) ?? e[0]} -> ${label.get(String(e[1])) ?? e[1]}${e[2] ? ` : ${e[2]}` : ""}`);
  }
  for (const [id, l] of label) if (!used.has(id)) out.push(l);
  return out.join("\n");
}

export function textToDiagram(text: string): { nodes: { id: string; label: string }[]; edges: any[] } {
  const ids = new Map<string, string>();
  const nodes: { id: string; label: string }[] = [];
  const edges: any[] = [];
  const node = (name: string) => {
    const key = name.trim().slice(0, 26);
    if (!key) return "";
    if (!ids.has(key)) {
      ids.set(key, `n${ids.size + 1}`);
      nodes.push({ id: `n${ids.size}`, label: key });
    }
    return ids.get(key)!;
  };
  for (const line of lines(text)) {
    if (!line.includes("->")) { node(line); continue; }
    const parts = line.split("->");
    const last = parts.pop() as string;
    const [lastName, ...lab] = last.split(":");
    const label = lab.join(":").trim();
    const names = [...parts, lastName];
    for (let i = 0; i < names.length - 1; i++) {
      const a = node(names[i]), b = node(names[i + 1]);
      if (a && b && a !== b) edges.push(i === names.length - 2 && label ? [a, b, label.slice(0, 22)] : [a, b]);
    }
  }
  return { nodes: nodes.slice(0, 8), edges };
}

export function chartToText(props: Record<string, any>): string {
  return (props.labels || []).map((l: string, i: number) => `${l}: ${(props.values || [])[i] ?? ""}`).join("\n");
}

export function textToChart(text: string): { labels: string[]; values: number[] } {
  const labels: string[] = [], values: number[] = [];
  for (const line of lines(text)) {
    const i = line.lastIndexOf(":");
    if (i < 0) continue;
    const v = Number(line.slice(i + 1).replace(/[, ]/g, ""));
    if (Number.isFinite(v) && line.slice(i + 1).trim() !== "") { labels.push(line.slice(0, i).trim().slice(0, 16)); values.push(v); }
  }
  return { labels: labels.slice(0, 8), values: values.slice(0, 8) };
}

export const timelineToText = (events: any[] = []) => events.map((e) => `${e.date || ""} | ${e.label || ""}`).join("\n");

export function textToTimeline(text: string): { date: string; label: string }[] {
  return lines(text).slice(0, 6).map((l) => {
    const i = l.indexOf("|");
    return i < 0 ? { date: "", label: l } : { date: l.slice(0, i).trim().slice(0, 12), label: l.slice(i + 1).trim().slice(0, 55) };
  });
}
