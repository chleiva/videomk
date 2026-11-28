// Create (docs/WEB_REDESIGN_2026.md 6.3): "What should we make?", ONE composer card: prompt, photo / presentation / voice buttons, three pills (made for, length, look), an Options
// popover for everything else, Create with its price. Everything the server offers comes from capabilities (docs/CREATE_API.md); the AI decides voice, music and pace.
// Same flow as the apps: request check (kind questions, or a polite "we can't make this") then generate; a retry can never bill twice (same request id).
import "../../styles/app-b.css";
import { useCallback, useEffect, useLayoutEffect, useMemo, useReducer, useRef, useState } from "react";
import { Sheet, Spinner } from "../ui";
import { AIcon as Icon, shapeGlyph } from "./icons";
import { hasFinishedVideo } from "./firstVideo";
import { Menu, Popover, Segmented } from "./Menu";
import DeckPicker, { useDeck } from "../DeckPicker";
import MediaPicker from "./MediaPicker";
import LookPicker from "./LookPicker";
import CreateLocked from "./CreateLocked";
import Shortcuts from "./Shortcuts";
import { useUploadQueue } from "./useUploadQueue";
import { useClipUploads } from "./useClipUploads";
import ClipSheet from "./ClipSheet";
import type { ClipPick } from "./ClipSheet";
import { ClipNotes, ClipTile, RecentClipsSheet } from "./ClipTile";
import { clipDeps } from "../../lib/videoClipDeps";
import { clipAnnouncementKey, looksLikeVideo, videoAssetsExtra, videoGate } from "../../lib/videoClips";
import type { Clip } from "../../lib/videoClips";
import { newRequestId, startGeneration, getWallet } from "../../lib/api";
import type { Wallet } from "../../lib/api";
import {
  FALLBACK_CAPS, LOOKS, MAX_VIDEO_PHOTOS, buildOptions, checkRequest, creditsFor, defaultForm, fourKAdvice, getCapabilities, lengthLabel, lengthMenu, loadSaved, mediaExtras, minutesForPhotos,
  normalize, overPlatformLimit, photoCapacity, pillValues, platformOf, qualityChoices, resolutionsFor, saveChoices, selectPlatform,
} from "../../lib/create";
import type { Answer, Capabilities, Form, Question } from "../../lib/create";
import { AUTO, loadLook, lookHints, normalizeChoice, optionOf, presetFor, rememberNote, saveLook } from "../../lib/looks";
import type { LookChoice } from "../../lib/looks";
import { createLock, planName } from "../../lib/plan";
import { DECK_ASPECT, deckAspectWarning, deckCredits, deckGenerateExtras, deckMinutes } from "../../lib/deck";
import { dictationSupported, speechLang, startDictation } from "../../lib/dictation";
import type { Dictation } from "../../lib/dictation";
import { betterAvailable, betterErrorKey, betterPreferred, DictationIds, recordingSupported, setBetterPreferred, showUpgradeHint, startBetter } from "../../lib/betterDictation";
import type { BetterHandle } from "../../lib/betterDictation";
import { announcementKey, effectiveLimitS, elapsedS, feedbackReduce, initialFeedback, LevelMeter, waitState, warningFor } from "../../lib/dictationFeedback";
import DictationPanel from "./DictationPanel";
import { APP_PATHS } from "../../lib/links";
import { rememberPrompt } from "../../lib/prompts";
import { pictureFiles } from "../../lib/upload";
import { directDeps } from "../../lib/uploadDeps";
import { useLocale } from "../../lib/useLocale";
import type { Photo } from "../../lib/library";

const EXAMPLES = ["create.example1", "create.example2", "create.example3"];   // three (the apps show the same three); two on a short window (CSS)
const MEDIA_SELECTION = "vmk_media_selection";   // My media keeps its ticked photos here while the composer is open, so Back returns to the same selection
const HANDOFF = "vmk_compose_library";       // My media -> "Make a video": the chosen photos wait here for the composer
// The scene-style row stays hidden until the server's VECTOR_SCENES switch is on in this environment (docs/VECTOR_SCENE_POLICY.md): set PUBLIC_SCENE_STYLE=1 at build time then.
const SCENE_STYLE_ON = ["1", "true", "on"].includes(String(((import.meta as any).env ?? {}).PUBLIC_SCENE_STYLE ?? "").toLowerCase());

type Stage =
  | { k: "form" }
  | { k: "checking" }
  | { k: "questions"; questions: Question[]; i: number; answers: Answer[] }
  | { k: "stop"; kind: "not_supported" | "blocked" | "paused"; message?: string; suggestion?: string };
interface LibPick { id: string; thumb_url: string }

function readHandoff(): LibPick[] {
  try {
    const raw = sessionStorage.getItem(HANDOFF);
    if (!raw) return [];
    sessionStorage.removeItem(HANDOFF);
    const a = JSON.parse(raw);
    return Array.isArray(a) ? a.filter((p: any) => typeof p?.id === "string").map((p: any) => ({ id: p.id, thumb_url: typeof p.thumb_url === "string" ? p.thumb_url : "" })).slice(0, MAX_VIDEO_PHOTOS) : [];
  } catch { return []; }
}

/** "Pro" with a small lock: a length (or anything else) the plan does not make. There is no buy button: nothing can be bought yet (`can_upgrade` is false). */
function PlanTag({ plan, t }: { plan: string | null; t: (k: string, p?: Record<string, string | number>) => string }) {
  return <span className="plan-tag"><Icon name="lock" size={14} />{plan && <span aria-hidden="true">{plan}</span>}<span className="sr-only-vmk">{plan ? t("create.plan_needs", { plan }) : t("create.plan_locked")}</span></span>;
}
/** "Landscape": a shape in the server's words. */
const shapeName = (id: string, c: Capabilities): string => c.aspects.find((a) => a.id === id)?.label ?? id;

export default function Composer() {
  const { t, locale } = useLocale();
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [live, setLive] = useState(false);
  const [form, setForm] = useState<Form | null>(null);
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [walletRead, setWalletRead] = useState(false);
  const [lookLine, setLookLine] = useState<string | null>(null);   // one line when a chosen look went back to Auto (photos or a deck were attached)
  const briefNote = useRef<string | undefined>(undefined);
  const [stage, setStage] = useState<Stage>({ k: "form" });
  const [hint, setHint] = useState<{ text: string; credits?: boolean; soft?: boolean } | null>(null);   // soft: a tap on the inactive Create said what is missing; it fades by itself
  const [finished, setFinished] = useState<boolean | null>(null);   // has this account finished a video (null: not known yet)
  const [sending, setSending] = useState(false);
  const [other, setOther] = useState("");
  const [picker, setPicker] = useState(false);
  const [libPicks, setLibPicks] = useState<LibPick[]>([]);
  const [previews, setPreviews] = useState<Record<string, string>>({});
  const [listening, setListening] = useState(false);
  const [micError, setMicError] = useState<null | "denied" | "language">(null);
  const [better, setBetter] = useState(() => betterPreferred());   // the person's choice in Options (default on)
  const [working, setWorking] = useState(false);                    // Better dictation: the clip is being turned into text
  const [micNote, setMicNote] = useState<string | null>(null);      // a short line after a fallback or the 6 minute stop
  const dictIds = useRef(new DictationIds());
  // dictation feedback: phase machine, real mic level, the handle for Cancel / Retry (docs/DICTATION_FEEDBACK_2026-11-28.md)
  const [fb, fbDispatch] = useReducer(feedbackReduce, undefined, initialFeedback);
  const meter = useRef(new LevelMeter(24));
  const bh = useRef<BetterHandle | null>(null);
  const voiceBase = useRef("");
  const [voice, setVoice] = useState<"better" | "native">("better");
  const [inserted, setInserted] = useState(false);
  const [announce, setAnnounce] = useState("");
  const [picked, setPicked] = useState<number | null>(null);   // the length chosen for a deck video (null: the deck's suggestion)
  const req = useRef<{ key: string; id: string }>({ key: "", id: "" });
  const area = useRef<HTMLTextAreaElement>(null);
  const files = useRef<HTMLInputElement>(null);
  const deckInput = useRef<HTMLInputElement>(null);
  const dict = useRef<Dictation | null>(null);
  const textNow = useRef("");
  const voiceVisible = fb.phase === "recording" || fb.phase === "transcribing" || fb.phase === "failed";
  useEffect(() => {   // clock for the timer and the wait hints (4 Hz is enough for a seconds display)
    if (fb.phase !== "recording" && fb.phase !== "transcribing") return;
    const id = setInterval(() => fbDispatch({ type: "tick", nowMs: Date.now() }), 250); return () => clearInterval(id);
  }, [fb.phase]);
  useEffect(() => { if (fb.phase === "inserted") { const id = setTimeout(() => fbDispatch({ type: "dismiss" }), 1300); return () => clearTimeout(id); } }, [fb.phase]);
  const akey = announcementKey(fb);
  useEffect(() => {   // screen-reader line: only when the state changes, never per tick
    const w = warningFor(fb);
    const text: Record<string, string> = { listening: t("create.voice_listening"), warn_soon: t("create.voice_soon_a11y", { s: w.remainingS }), warn_final: t("create.voice_final_a11y"), transcribing: t("create.voice_wait_a11y"), slow: t("create.voice_slow_a11y"), failed: t("create.voice_failed_a11y"), inserted: t("create.voice_inserted_a11y") };
    if (akey) setAnnounce(text[akey] ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [akey]);   // what the box holds right now: dictation reads it to notice hand edits
  const urls = useRef<string[]>([]);
  const topEl = useRef<HTMLDivElement>(null);   // prompt, photos, notes: locked (inert, dimmed) while a request is checked or sent
  const toolRow = useRef<HTMLDivElement>(null);
  const checkRun = useRef(0);   // a request check that was cancelled must not act when its answer arrives late

  const photos = useUploadQueue(directDeps);
  // the person's own video clips (docs/VIDEO_UPLOAD_CLIENTS_2026-11-28.md): sent to capabilities.video_upload.api_url, shown in the same strip as the photos
  const vcaps = caps?.video_upload;
  const clipDepsNow = useMemo(() => (vcaps ? clipDeps(vcaps.apiUrl) : null), [vcaps?.apiUrl]); // eslint-disable-line react-hooks/exhaustive-deps
  const clips = useClipUploads(clipDepsNow);
  const [clipFile, setClipFile] = useState<File | null>(null);     // the picked video, while the "Add a video" dialog is open
  const [recent, setRecent] = useState(false);
  const videoInput = useRef<HTMLInputElement>(null);
  const recordInput = useRef<HTMLInputElement>(null);
  const clipKey = clipAnnouncementKey(clips.items);
  useEffect(() => {   // screen-reader line for a clip: when its state changes, never per progress tick
    const k = clipKey.split(":")[0];
    const text: Record<string, string> = { up: t("create.clip_a11y_up"), check: t("create.clip_checking"), slow: t("create.clip_slow"), ready: t("create.clip_a11y_ready"), bad: t("create.clip_a11y_bad") };
    if (k && text[k]) setAnnounce(text[k]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clipKey]);
  const clipsReadyN = clips.items.filter((i) => i.state === "ready").length;
  useEffect(() => { if (clipsReadyN > 0) void getCapabilities().then((x) => { if (x) setCaps(x); }); }, [clipsReadyN]);   // today's clips left changed
  const lockedNow = sending || stage.k === "checking";
  useEffect(() => { const el = topEl.current; if (!el) return; el.toggleAttribute("inert", lockedNow); if (lockedNow) (document.activeElement as HTMLElement | null)?.blur?.(); }, [lockedNow]);

  useEffect(() => { if (!hint?.soft) return; const id = window.setTimeout(() => setHint(null), 4500); return () => window.clearTimeout(id); }, [hint]);

  useEffect(() => {
    let alive = true;
    const qs = new URLSearchParams(location.search);
    const prompt = qs.get("prompt")?.slice(0, 500) ?? "";
    getCapabilities().then((c) => {
      if (!alive) return;
      const cc = c ?? FALLBACK_CAPS; setLive(!!c); setCaps(cc);
      // "Make another" on the video page opens Create with one thing changed (shape, length or language); anything the stack does not offer is ignored
      const pre: Partial<Form> = {};
      const a = qs.get("aspect"), m = Number(qs.get("minutes")), l = qs.get("language");
      if (a && cc.aspects.some((x) => x.id === a && x.ready)) pre.aspect = a;
      if (m > 0 && m <= 12) pre.minutes = m;
      if (l && cc.languages.some((x) => x.id === l)) pre.language = l;
      setForm(normalize({ ...defaultForm(cc, loadSaved()), pick: loadLook() ?? AUTO, ...pre, text: prompt }, cc));   // the look chosen last time, when it is still offered
    });
    getWallet().then((w) => { if (alive) { setWallet(w); setWalletRead(true); } });
    hasFinishedVideo().then((v) => { if (alive) setFinished(v); });
    setLibPicks(readHandoff());
    return () => { alive = false; dict.current?.stop(); urls.current.forEach((u) => URL.revokeObjectURL(u)); };
  }, []);

  const c = caps ?? FALLBACK_CAPS;
  const f = form;
  textNow.current = f?.text ?? "";
  const set = useCallback((patch: Partial<Form>) => setForm((x) => (x ? normalize({ ...x, ...patch }, c) : x)), [c]);
  const deck = useDeck(c.deck);
  const ready = deck.state.k === "ready" ? deck.state : null;
  const deckId = ready?.id;
  useEffect(() => { setPicked(null); if (deckId) setForm((x) => (x ? normalize({ ...x, aspect: DECK_ASPECT }, c) : x)); }, [deckId]); // eslint-disable-line react-hooks/exhaustive-deps
  const deckActive = deck.state.k !== "idle";
  const busyDeck = deck.state.k === "uploading" || deck.state.k === "processing";

  // ---- photos
  const directReady = photos.queue.readyIds();
  const directItems = photos.items.filter((i) => i.state !== "cancelled");
  const addingPhotos = photos.items.some((i) => i.state === "queued" || i.state === "preparing" || i.state === "uploading");
  const totalPhotos = directItems.filter((i) => i.state !== "failed" && i.state !== "unsupported" && i.state !== "no_space").length + libPicks.length;
  const room = Math.max(0, MAX_VIDEO_PHOTOS - totalPhotos);
  // ---- clips: photos and clips share the strip; a clip that failed or was refused does not count toward the video's limit
  const clipItems = clips.items;
  const clipCount = clipItems.filter((i) => i.state !== "failed" && i.state !== "rejected" && i.state !== "cancelled").length;
  const clipsBusy = clipItems.some((i) => i.state === "hashing" || i.state === "uploading" || i.state === "analysing");
  const clipRoom = vcaps ? Math.max(0, vcaps.clipsPerVideo - clipCount) : 0;
  const gateV = vcaps ? videoGate(vcaps) : null;
  const clipReady = clipItems.filter((i) => i.state === "ready").length;
  const stripEmpty = directItems.length === 0 && libPicks.length === 0 && clipItems.length === 0;
  const canRecord = useMemo(() => { try { return typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches; } catch { return false; } }, []);

  // ---- the look: a look that is not made from the person's own photos or slides goes back to Auto when they are attached, with one line that says so
  const lookCtx = useMemo(() => ({ photos: totalPhotos > 0 || clipCount > 0, deck: deckActive }), [totalPhotos, clipCount, deckActive]);
  const pick = f?.pick ?? AUTO;
  useEffect(() => {
    if (!c.looks) return;
    const n = normalizeChoice(pick, c.looks, lookCtx);
    if (!n.reset) return;
    setLookLine(t(n.reset === "deck" ? "create.pick_reset_deck" : "create.pick_reset_photos", { look: optionOf(c.looks, pick.look)?.label ?? "", auto: t("create.look_auto") }));
    setForm((x) => (x ? { ...x, pick: AUTO } : x));
  }, [lookCtx, pick, c.looks]); // eslint-disable-line react-hooks/exhaustive-deps
  const choosePick = (next: LookChoice) => { setLookLine(null); saveLook(next); set({ pick: next }); };

  function addFiles(list: FileList | File[] | null | undefined) {
    const pics = pictureFiles(list ? Array.from(list) : []);
    if (!pics.length) return;
    const take = pics.slice(0, room);
    if (take.length < pics.length) setHint({ text: t("create.photos_max", { n: MAX_VIDEO_PHOTOS }) });
    if (!take.length) return;
    const keys = photos.queue.add(take);
    const next: Record<string, string> = {};
    keys.forEach((k, i) => { const u = URL.createObjectURL(take[i]); urls.current.push(u); next[k] = u; });
    setPreviews((p) => ({ ...p, ...next }));
  }
  /** A video was picked, dropped or pasted: the dialog asks the two questions before anything is uploaded. Only when the server offers it and it is open. */
  function pickVideo(list: File[]) {
    if (!vcaps || !list.length) return;
    if (gateV && !gateV.open) { setHint({ text: t(gateV.reason === "paused" ? "create.clip_locked_paused" : gateV.reason === "quota" ? "create.clip_locked_quota" : "create.clip_locked_plan", { plan: nameOfPlan(gateV.plan) ?? gateV.plan ?? "" }) }); return; }
    if (clipRoom <= 0) { setHint({ text: t("create.clip_max", { n: vcaps.clipsPerVideo }) }); return; }
    if (list.length > 1) setHint({ text: t("create.clip_one_at_a_time"), soft: true });
    setClipFile(list[0]);
  }
  function addClip(p: ClipPick) {
    setClipFile(null);
    if (p.poster) urls.current.push(p.poster);
    clips.uploader?.add({ blob: p.blob, name: p.name, contentType: p.contentType, useAudio: p.useAudio, poster: p.poster, aspect: p.aspect, trimmedLocally: p.trimmedLocally });
  }
  function useRecent(c: Clip) { setRecent(false); clips.uploader?.addReady(c); }
  /** What a drop or a paste brought: pictures to the photo queue, the first video to the dialog. */
  function addMixed(list: File[]) {
    const vids = vcaps ? list.filter(looksLikeVideo) : [];
    if (vids.length) pickVideo(vids);
    addFiles(list.filter((f) => !vids.includes(f)));
  }
  function removePhoto(key: string) { photos.queue.remove(key); const u = previews[key]; if (u) { URL.revokeObjectURL(u); setPreviews((p) => { const { [key]: _x, ...rest } = p; return rest; }); } }

  // ---- dictation (only where the browser has it)
  const canDictate = useMemo(() => dictationSupported(), []);
  const useBetter = better && betterAvailable(caps?.dictation) && recordingSupported();
  const buzz = (ms: number) => { try { navigator.vibrate?.(ms); } catch { /* not on this device */ } };   // a subtle tick where the browser has haptics
  function cancelVoice() {
    if (voice === "better") bh.current?.cancel();
    else { dict.current?.stop(); setForm((x) => (x ? { ...x, text: voiceBase.current } : x)); }
    setListening(false); setWorking(false); fbDispatch({ type: "cancel" }); setAnnounce(t("create.voice_cancelled_a11y")); area.current?.focus();
  }
  async function toggleDictation() {
    if (working) return;
    if (listening) { dict.current?.stop(); return; }
    setMicError(null); setMicNote(null);
    voiceBase.current = textNow.current; fbDispatch({ type: "request" }); meter.current.reset();
    if (useBetter && caps?.dictation) {
      const dc = caps.dictation, limitS = effectiveLimitS(dc.maxClipSeconds, dc.secondsLeft);
      setListening(true); setVoice("better");
      const h = await startBetter({
        lang: speechLang(locale), languages: [locale === "es" ? "es" : "en"], getText: () => textNow.current,
        setText: (text) => setForm((x) => (x ? { ...x, text } : x)), maxLength: 1500, maxSeconds: limitS || dc.maxClipSeconds, maxBytes: dc.maxClipBytes,
        onLevel: (l) => meter.current.push(l),
        onWorking: () => { setListening(false); setWorking(true); fbDispatch({ type: "stop", nowMs: Date.now() }); fbDispatch({ type: "retry", nowMs: Date.now() }); },
        onRetryable: (kind) => { fbDispatch({ type: "fail", kind }); buzz(20); },
        onResult: (r) => {
          setWorking(false); setListening(false); dict.current = null; bh.current = null;
          if (r.denied) { setMicError("denied"); fbDispatch({ type: "denied" }); }
          else if (r.cancelled) fbDispatch({ type: "cancel" });
          else if (r.id) { dictIds.current.add(r.id); fbDispatch({ type: "ok" }); setInserted(true); setTimeout(() => setInserted(false), 1300); buzz(10); if (r.limit) setMicNote(t("create.better_limit")); }
          else { fbDispatch({ type: "cancel" }); const k = r.kind ? betterErrorKey(r.kind) : null; setMicNote(r.limit ? t("create.better_limit") : k ? t(k) : null); }
          area.current?.focus();
          if (r.kind === "quota" || r.kind === "plan" || r.kind === "paused") void getCapabilities().then((x) => { if (x) setCaps(x); });
        },
      });
      if (h) { dict.current = h; bh.current = h; fbDispatch({ type: "granted", nowMs: Date.now(), limitS: limitS || dc.maxClipSeconds }); buzz(10); } else { setListening(false); fbDispatch({ type: "denied" }); }
      return;
    }
    setVoice("native");
    const d = startDictation({
      lang: speechLang(locale),
      getText: () => textNow.current,
      setText: (text) => setForm((x) => (x ? { ...x, text } : x)),
      maxLength: 1500,
      onEnd: (why) => { setListening(false); fbDispatch({ type: "cancel" }); if (why === "denied") setMicError("denied"); else if (why === "language") setMicError("language"); area.current?.focus(); },
    });
    if (d) { dict.current = d; setListening(true); fbDispatch({ type: "granted", nowMs: Date.now(), limitS: 300 }); buzz(10); } else { setMicError("denied"); fbDispatch({ type: "denied" }); }
  }

  // ---- price
  const minutes = f ? (ready ? deckMinutes(ready, picked) : f.minutes) : 1;
  const credits = f ? (ready ? deckCredits(ready, picked, f.resolution, c) : creditsFor(f.minutes, f.resolution, c)) : 1;
  const enough = wallet ? wallet.unlimited || wallet.balance >= credits : true;
  const advice = f ? fourKAdvice(f, c) : null;
  const limit = f ? overPlatformLimit({ ...f, minutes }, c) : null;
  const platform = f ? platformOf(c, f.platform) : undefined;
  const capacity = photoCapacity(minutes);
  const looks = c.looks;
  const lh = f && looks && !ready ? lookHints(f.pick, looks, minutes * 60, f.aspect) : null;
  const lookName = looks ? optionOf(looks, pick.look)?.label ?? "" : "";
  const longer = lh ? presetFor(Math.max(lh.minSeconds ?? 0, lh.conversationSeconds ?? 0), c.lengths.presets, c.limits?.planMaxSeconds) : null;
  const gate = walletRead ? createLock(wallet, c.plans) : null;
  const nameOfPlan = (id: string | null) => planName(wallet?.plans ?? c.plans, id);
  const fitHint = totalPhotos > capacity ? (() => { const better = minutesForPhotos(totalPhotos, c); return better ? t("create.photos_fit_better", { n: capacity, total: totalPhotos, length: lengthLabel(minutes), better: lengthLabel(better) }) : t("create.photos_fit", { n: capacity, total: totalPhotos, length: lengthLabel(minutes) }); })() : null;

  // Create sits at the end of the tool row. When the row cannot hold the tools and Create (large text, zoom, a narrow window) Create moves to a row of its own, full width:
  // the layout the brief keeps as the fallback. Measured, not guessed: class off, does Create wrap? class on if so. Synchronous, so nothing flashes.
  useLayoutEffect(() => {
    const row = toolRow.current; if (!row) return;
    const measure = () => {
      const go = row.querySelector<HTMLElement>(".compose-go"), cl = row.querySelector<HTMLElement>(".tool-cluster"); if (!go || !cl) return;
      row.classList.remove("is-stacked");
      const say = row.querySelector<HTMLElement>(".tool-listening");
      row.classList.toggle("is-stacked", go.getBoundingClientRect().top > cl.getBoundingClientRect().top + 8 || (!!say && say.scrollWidth > say.clientWidth + 1));
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure); ro.observe(row.parentElement ?? row);
    return () => ro.disconnect();
  }, [!!f && !!caps, locale, listening, credits, totalPhotos, deckActive, lockedNow]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- sending
  const options = () => buildOptions(f!, c, live, lookCtx);
  async function generate(brief?: Record<string, string>) {
    if (!f) return;
    setSending(true); setHint(null); setStage({ k: "form" });
    const text = f.text.trim();
    const { target_minutes: _len, ...rest } = options();
    const base = ready ? { ...rest, ...deckGenerateExtras(ready.id, picked) } : options();
    const sent = { ...base, ...(ready ? {} : { ...mediaExtras(directReady, libPicks.map((p) => p.id), photos.queue.metaById()), ...videoAssetsExtra(clips.uploader?.readyIds() ?? [], vcaps?.clipsPerVideo) }), ...dictIds.current.extra() };
    const key = JSON.stringify([text, sent, brief ?? null]);
    if (req.current.key !== key) req.current = { key, id: newRequestId() };   // same request, same id: a retry cannot bill twice
    try {
      const r = await startGeneration(text, req.current.id, { ...sent, ...(brief ? { brief } : {}) });
      if (!r.ok) {
        setSending(false);
        if (ready && r.kind === "invalid" && r.code?.startsWith("deck_") && r.code !== "deck_not_ready") { deck.reportError(r.code, ready.name); return; }
        if (r.kind === "blocked" || r.kind === "paused") setStage({ k: "stop", kind: r.kind, message: r.message });
        else setHint({ text: r.message, credits: r.kind === "credits" });   // a plan refusal (403 plan_*, 429 free_budget_spent) is the server's own sentence, shown here; the draft stays as it is
        return;
      }
      dictIds.current.clear();   // those dictations now belong to this video
      if (!ready) saveChoices(f);
      rememberPrompt(r.videoId, text);   // the video page shows the sentence that made it
      rememberNote(r.videoId, r.look?.note ?? briefNote.current);   // "Made from your photos: the Cartoon look is not used..." is shown while the video is made
      try { sessionStorage.removeItem(MEDIA_SELECTION); } catch { /* private mode */ }   // the photos were used: My media starts clean
      location.assign(`${APP_PATHS.videos}?started=1`);
    } catch (e) {
      console.error(e);
      setSending(false); setHint({ text: t("gen.start_error") });
    }
  }

  async function submit(e?: React.FormEvent) {
    e?.preventDefault();
    if (!f || sending || stage.k !== "form" || busyDeck || addingPhotos || clipsBusy || listening) return;
    const text = f.text.trim();
    if (ready) {
      if (!enough) { setHint({ text: t("create.not_enough", { needed: credits, balance: wallet?.balance ?? 0 }), credits: true }); return; }
      await generate(); return;   // the prompt is optional with a deck; the deck is checked on the server
    }
    if (!text) { setHint({ text: t("create.need_text"), soft: true }); area.current?.focus(); return; }   // the inactive Create stays tappable: it says what is missing
    if (text.length < 15) { setHint({ text: t("gen.more_detail") }); area.current?.focus(); return; }
    if (!enough) { setHint({ text: t("create.not_enough", { needed: credits, balance: wallet?.balance ?? 0 }), credits: true }); return; }
    if (!live || c.intake === false) { await generate(); return; }
    setHint(null); setStage({ k: "checking" });
    const run = ++checkRun.current;
    briefNote.current = undefined;
    const out = await checkRequest(text, options(), []);
    if (run !== checkRun.current) return;   // cancelled meanwhile: the form is already back, untouched
    followBrief(out, []);
  }
  /** Cancel while the request is being checked: nothing was sent to be made yet, so the form simply comes back as it was. */
  function cancelCheck() { if (stage.k !== "checking" || sending) return; checkRun.current++; setStage({ k: "form" }); setTimeout(() => area.current?.focus(), 20); }
  function followBrief(out: Awaited<ReturnType<typeof checkRequest>>, answers: Answer[]) {
    if (out.status === "ok") briefNote.current = out.note;
    if (out.status === "questions") { setOther(""); setStage({ k: "questions", questions: out.questions, i: 0, answers }); }
    else if (out.status === "ok") void generate(out.brief);
    else setStage({ k: "stop", kind: out.status, message: out.message, suggestion: out.status === "not_supported" ? out.suggestion : undefined });
  }
  async function answer(a: Answer) {
    if (stage.k !== "questions" || !f) return;
    const answers = [...stage.answers, a];
    if (stage.i + 1 < stage.questions.length) { setOther(""); setStage({ ...stage, i: stage.i + 1, answers }); return; }
    await finish(answers);
  }
  async function finish(answers: Answer[]) {
    if (!f) return;
    setStage({ k: "checking" });
    const run = ++checkRun.current;
    const out = await checkRequest(f.text.trim(), options(), answers);
    if (run !== checkRun.current) return;
    if (out.status === "ok") briefNote.current = out.note;
    if (out.status === "ok") void generate(out.brief); else if (out.status === "questions") void generate(); else followBrief(out, answers);   // asked enough: make it
  }

  // ---- screens
  if (!f || !caps) return <section className="page compose"><p className="muted" role="status"><Spinner /> {t("gen.loading")}</p></section>;
  if (gate) return <CreateLocked lock={gate} plan={(wallet?.plans ?? c.plans)?.plan?.name ?? null} />;

  const pv = pillValues(f, c, t("create.other_platform"));
  const lookLabel = (l: string) => t(`create.look_${l}`);
  const aspects = c.aspects.filter((a) => a.ready);
  // For: the platforms the server lists, then the shapes no platform starts with (Square, Portrait): the Format row of the Options sheet moved here, so a shape is chosen in ONE place
  const extraShapes = aspects.filter((a) => !c.platforms.some((p) => p.id !== "other" && p.aspect === a.id));
  const onShape = f.platform === "other" && extraShapes.some((a) => a.id === f.aspect);
  const forItems = [
    ...c.platforms.map((p) => ({ id: p.id, label: p.id === "other" ? t("create.other_platform") : p.label, checked: f.platform === p.id && !onShape })),
    ...extraShapes.map((a) => ({ id: `shape:${a.id}`, label: a.label, checked: onShape && f.aspect === a.id })),
  ];
  const forLabel = onShape ? shapeName(f.aspect, c) : pv.for;
  const lenRows = lengthMenu(c, f);
  const lengthItems = [
    ...(ready ? [{ id: "suggested", label: t("deck.suggested_chip", { length: lengthLabel(ready.suggested_minutes) }), checked: picked === null }] : []),
    ...lenRows.filter((r) => !ready || r.minutes !== ready.suggested_minutes).map((r) => ({ id: String(r.minutes), label: lengthLabel(r.minutes), detail: r.locked ? <PlanTag plan={nameOfPlan(r.locked.requires)} t={t} /> : <span className="vm-menu-price">{t("create.credits", { n: ready ? deckCredits({ ...ready, suggested_minutes: r.minutes }, r.minutes, f.resolution, c) : r.credits })}</span>, checked: ready ? picked === r.minutes : f.minutes === r.minutes, disabled: r.over || !!r.locked })),
  ];
  const lookItems = LOOKS.map((l) => ({ id: l, label: <span className="look-item"><i className={`swatch swatch-${l}`} aria-hidden="true" />{lookLabel(l)}</span>, checked: f.look === l }));
  const wm = c.watermark;
  const quality = qualityChoices(c, f);
  const questionTitle = stage.k === "questions" ? t("create.questions_title") : stage.k === "stop" ? (stage.kind === "paused" ? t("create.paused_title") : t("create.cant_make_title")) : "";
  const locked = sending || stage.k === "checking";   // from the tap until the answer: nothing on the form can change, and it says what is happening
  const canSend = !sending && !busyDeck && !addingPhotos && !clipsBusy && stage.k === "form" && (ready ? true : f.text.trim().length > 0);
  const inactive = !canSend || listening;   // Create stays tappable: the tap says what is missing (opaque fill, no glow)
  const why = listening ? "create.state_listening" : addingPhotos || clipsBusy || busyDeck ? "create.state_wait" : "create.state_need_text";
  const costWords = t("create.credits", { n: credits });
  const empty = !f.text.trim() && !deckActive && totalPhotos === 0;
  // the price is taught once: until this account has a finished video, "2 credits. You have 11."; afterwards the balance lives in the header chip and shows here only when low
  const spendable = wallet && !wallet.unlimited && enough;
  const caption = !spendable || locked || hint ? null : finished === false ? t("create.first_caption", { credits: costWords, balance: wallet!.balance }) : wallet!.balance < 2 * credits ? t("create.credits_left", { n: wallet!.balance }) : null;

  return (
    <section className="page compose">
      <div className="compose-aura" aria-hidden="true" />
      <div className="compose-head">
        <h1 className="compose-title">{t("create.heading")}</h1>
      </div>

      <form className={`composer-card ${locked ? "is-locked" : ""}`} aria-busy={locked} onSubmit={submit} onDragOver={(e) => { if (e.dataTransfer.types.includes("Files")) e.preventDefault(); }} onDrop={(e) => { if (e.dataTransfer.files.length) { e.preventDefault(); addMixed(Array.from(e.dataTransfer.files)); } }}>
        <div className="composer-top" ref={topEl}>
        <label htmlFor="create-text" className="sr-only-vmk">{t("create.prompt_label")}</label>
        <textarea id="create-text" ref={area} data-autofocus autoFocus rows={3} className={`compose-text ${inserted ? "is-inserted" : ""}`} value={f.text} readOnly={listening} maxLength={1500} placeholder={ready ? t("deck.placeholder") : t("create.placeholder")} aria-describedby="create-hint"
          onChange={(e) => { setHint(null); set({ text: e.target.value }); }}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); void submit(); } }}
          onPaste={(e) => { const all = Array.from(e.clipboardData.files); if (pictureFiles(all).length || (vcaps && all.some(looksLikeVideo))) { e.preventDefault(); addMixed(all); } }} />

        {!stripEmpty && (
          <div className="attach-strip" role="list" aria-label={[totalPhotos > 0 ? t("create.photos_n", { n: totalPhotos }) : "", clipItems.length ? t("create.clip_n", { n: clipItems.length }) : ""].filter(Boolean).join(", ")}>
            {libPicks.map((p) => (
              <div key={p.id} role="listitem" className="attach"><img src={p.thumb_url} alt="" /><button type="button" className="attach-x" aria-label={t("create.photo_remove")} onClick={() => setLibPicks((x) => x.filter((y) => y.id !== p.id))}><Icon name="close" size={14} /></button></div>
            ))}
            {directItems.map((i) => (
              <div key={i.key} role="listitem" className={`attach is-${i.state}`}>
                {previews[i.key] && <img src={previews[i.key]} alt="" />}
                {(i.state === "preparing" || i.state === "uploading" || i.state === "queued") && <span className="attach-busy" aria-hidden="true"><Spinner /></span>}
                {(i.state === "failed" || i.state === "unsupported" || i.state === "no_space") && <span className="attach-bad" aria-hidden="true">!</span>}
                <button type="button" className="attach-x" aria-label={t("create.photo_remove")} onClick={() => removePhoto(i.key)}><Icon name="close" size={14} /></button>
              </div>
            ))}
            {clipItems.map((i) => <ClipTile key={i.key} item={i} t={t} used={vcaps?.usedSeconds} onRemove={() => clips.uploader?.remove(i.key)} />)}
            <p className="attach-count">{[totalPhotos > 0 || clipItems.length === 0 ? t("create.photos_n", { n: totalPhotos }) : "", clipItems.length ? t("create.clip_n", { n: clipItems.length }) : ""].filter(Boolean).join(" · ")}</p>
          </div>
        )}
        {clipItems.length > 0 && <ClipNotes items={clipItems} t={t} onRetry={(k) => clips.uploader?.retry(k)} onRemove={(k) => clips.uploader?.remove(k)} />}
        {clipItems.some((i) => i.state === "ready" || i.state === "analysing" || i.state === "uploading") && <p className="hint">{t("create.clip_use_line")}</p>}
        {(photos.summary.unsupported > 0 || photos.summary.failed > 0) && (
          <p className="hint hint-bad" role="status">
            {photos.summary.unsupported > 0 && t("create.photos_unreadable", { n: photos.summary.unsupported })} {photos.summary.failed > 0 && <>{t("create.photos_failed", { n: photos.summary.failed })} <button type="button" className="cost-link" onClick={() => photos.queue.retryFailed()}>{t("create.photos_retry")}</button></>}
          </p>
        )}

        {deckActive && c.deck && live && <DeckPicker caps={c.deck} deck={deck} />}

        {/* status: only what there is to say (nothing persistent: the placeholder says what to do) */}
        <div className="sr-only-vmk" role="status" aria-live="polite">{announce}</div>
        <div className="compose-notes" aria-live="polite">
          {micNote && !micError && <p className="hint" role="status">{micNote}</p>}
          {micError && <p className="hint hint-bad" role="status">{t(micError === "language" ? "create.dictate_language" : "create.dictate_denied")}</p>}
          {hint && <p id="create-hint" className="hint hint-bad" role="status">{hint.text}{hint.credits && <> <a href={APP_PATHS.credits}>{t("create.see_credits")}</a></>}</p>}
          {!hint && <p id="create-hint" className="sr-only-vmk" />}
          {!hint && wallet && !wallet.unlimited && !enough && <p className="hint">{t("create.not_enough", { needed: credits, balance: wallet.balance })} <a href={APP_PATHS.credits}>{t("create.see_credits")}</a></p>}
          {limit != null && platform && <p className="hint">{t("create.max_length", { platform: platform.label, length: lengthLabel(limit) })}</p>}
          {fitHint && <p className="hint">{fitHint}</p>}
          {advice && <p className="hint">{advice}</p>}
          {lh?.minSeconds != null && <p className="hint">{t("create.pick_min", { look: lookName, length: lengthLabel(lh.minSeconds / 60) })}{longer != null && <> <button type="button" className="cost-link" onClick={() => set({ minutes: longer })}>{t("create.pick_use", { length: lengthLabel(longer) })}</button></>}</p>}
          {lh?.minSeconds == null && lh?.conversationSeconds != null && <p className="hint">{t("create.pick_talk_min", { length: lengthLabel(lh.conversationSeconds / 60) })}{longer != null && <> <button type="button" className="cost-link" onClick={() => set({ minutes: longer })}>{t("create.pick_use", { length: lengthLabel(longer) })}</button></>}</p>}
          {lh?.bestAspects && <p className="hint">{t("create.pick_best", { look: lookName, shape: shapeName(lh.bestAspects[0], c) })} <button type="button" className="cost-link" onClick={() => set({ aspect: lh.bestAspects![0] })}>{t("create.pick_use_shape", { shape: shapeName(lh.bestAspects[0], c) })}</button></p>}
          {ready && deckAspectWarning(f.aspect) && <p className="hint">{t("deck.vertical_warn")} <button type="button" className="cost-link" onClick={() => set({ aspect: DECK_ASPECT })}>{t("deck.use_landscape")}</button></p>}
        </div>

        {lookLine && <p className="look-reset" role="status">{lookLine}</p>}{/* right above the pill it explains; it goes with the next choice */}
        </div>

        {locked ? (
          <div className="create-capsule" role="status">
            <Spinner /><span>{sending ? t("create.starting") : t("create.checking")}</span>
            {!sending && <button type="button" className="btn btn-line btn-sm" onClick={cancelCheck}>{t("create.cancel")}</button>}
          </div>
        ) : voiceVisible ? (
          <DictationPanel phase={fb.phase as "recording" | "transcribing" | "failed"} engine={voice} meter={meter.current} elapsedS={elapsedS(fb)} remainingS={warningFor(fb).remainingS} warning={warningFor(fb).level} slow={waitState(fb) !== "normal"} t={t}
            onStop={() => dict.current?.stop()} onCancel={cancelVoice} onRetry={() => bh.current?.retry()} onDevice={() => bh.current?.dismiss()} />
        ) : (
          <div className="composer-bar">
            {/* ONE row of pills (made for, length, look; the Characters pill only when the look has a cast). A fifth control never goes here: extras live in Options. */}
            <div className="composer-pills">
              {c.platforms.length > 0 && <Menu label={t("create.pill_for")} triggerClass="pill" trigger={<><Icon name={shapeGlyph(f.aspect)} size={16} className="pill-glyph" /><span className="pill-v">{forLabel}</span><Icon name="chevdown" size={16} /></>} items={forItems}
                onPick={(id) => (id.startsWith("shape:") ? setForm(normalize({ ...f, platform: "other", aspect: id.slice(6) }, c)) : setForm(selectPlatform(f, c, id)))} />}
              <Menu label={t("create.pill_length")} triggerClass="pill" trigger={<><Icon name="clock" size={16} className="pill-glyph" /><span className="pill-v">{ready ? lengthLabel(minutes) : pv.length}</span><Icon name="chevdown" size={16} /></>} items={lengthItems}
                onPick={(id) => (ready ? setPicked(id === "suggested" ? null : Number(id)) : set({ minutes: Number(id) }))} />
              {looks ? <LookPicker caps={looks} choice={pick} ctx={lookCtx} planName={nameOfPlan} onChange={choosePick} /> : <Menu label={t("create.pill_look")} triggerClass="pill" trigger={<><Icon name="sparkle" size={16} className="pill-glyph" /><span className="pill-v">{lookLabel(f.look)}</span><Icon name="chevdown" size={16} /></>} items={lookItems} onPick={(id) => set({ look: id as Form["look"] })} />}
            </div>

            {/* ONE tool row: photo, mic and Options on the left, Create (with its price) at the trailing end */}
            <div className="composer-tools" ref={toolRow}>
              <div className="tool-cluster">
                {!deckActive && (
                  <Menu label={t(vcaps ? "create.add_media" : "create.add_photos")} className="tool" triggerClass="icon-btn tool-btn" disabled={listening} trigger={<><Icon name="addphoto" size={22} />{totalPhotos + clipItems.length > 0 && <span className="tool-badge" aria-hidden="true">{totalPhotos + clipItems.length}</span>}</>} align="start"
                    items={[{ id: "device", label: t(vcaps ? "create.photos_from_device" : "create.from_device"), disabled: room === 0 }, { id: "media", label: t(vcaps ? "create.photos_from_media" : "create.from_media"), disabled: room === 0 },
                      ...(vcaps && gateV ? [{ id: "video", disabled: !gateV.open || clipRoom === 0, label: <span className="clip-menu-l">{t("create.add_video")}{!gateV.open && <small className="clip-menu-why">{t(gateV.reason === "paused" ? "create.clip_locked_paused" : gateV.reason === "quota" ? "create.clip_locked_quota" : "create.clip_locked_plan", { plan: nameOfPlan(gateV.plan) ?? gateV.plan ?? "" })}</small>}</span> },
                        ...(canRecord && gateV.open ? [{ id: "record", label: t("create.record_video"), disabled: clipRoom === 0 }] : []),
                        ...(gateV.open || clipItems.length ? [{ id: "recent", label: t("create.recent_clips"), disabled: clipRoom === 0 || !gateV.open }] : [])] : []),
                      ...(c.deck && live ? [{ id: "deck", label: t("deck.add_title"), disabled: totalPhotos > 0 || clipCount > 0 || busyDeck }] : [])]}
                    onPick={(id) => { if (id === "device") files.current?.click(); else if (id === "media") setPicker(true); else if (id === "video") videoInput.current?.click(); else if (id === "record") recordInput.current?.click(); else if (id === "recent") setRecent(true); else deckInput.current?.click(); }} />
                )}
                {(canDictate || useBetter) && <button type="button" className={`icon-btn tool-btn ${listening ? "is-live" : ""}`} aria-label={listening ? t("create.dictate_stop") : t("create.dictate")} title={listening ? t("create.dictate_stop") : t("create.dictate")} onClick={() => void toggleDictation()} disabled={working}><Icon name={listening ? "stop" : "mic"} size={22} /></button>}
                {live && (
                  <Popover label={t("create.options")} className="opts-root" triggerClass="tool-btn tool-options" disabled={listening} trigger={<><Icon name="sliders" size={22} /><span className="tool-options-label">{t("create.options")}</span></>}>
                    {(close) => (
                      <div className="opts">
                        <div className="opts-head"><h2 className="h2">{t("create.options")}</h2><button type="button" className="btn btn-tonal btn-sm" onClick={close}>{t("create.done")}</button></div>
                        {quality.length > 1 && <div className="opt"><p className="label">{t("create.resolution")}</p><Segmented label={t("create.resolution")} value={f.resolution} options={quality.map((r) => ({ id: r.id, label: r.label, disabled: r.available === false, hint: r.available === false ? nameOfPlan(r.requires_plan ?? null) ?? undefined : r.credits_multiplier > 1 ? `${r.credits_multiplier}×` : undefined }))} onChange={(v) => set({ resolution: v })} />
                          {resolutionsFor(c, f.aspect).find((r) => r.id === f.resolution)?.credits_multiplier! > 1 && <p className="hint">{t("create.cost_4k_double")}</p>}</div>}
                        <label className="opt-row" htmlFor="o-captions"><span>{t("create.subtitles")}</span><input id="o-captions" type="checkbox" role="switch" className="vm-switch" checked={f.captions} onChange={(e) => set({ captions: e.target.checked })} /></label>
                        {c.languages.length > 0 && <label className="opt-row" htmlFor="o-lang"><span>{t("create.narration")}</span><select id="o-lang" className="field field-inline" value={f.language} onChange={(e) => set({ language: e.target.value })}><option value="auto">{t("create.lang_auto")}</option>{c.languages.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}</select></label>}
                        {looks && <div className="opt"><p className="label">{t("create.colors")}</p><Segmented label={t("create.colors")} value={f.look} options={LOOKS.map((l) => ({ id: l, label: lookLabel(l) }))} onChange={(v) => set({ look: v })} /></div>}
                        {SCENE_STYLE_ON && !looks && !ready && <div className="opt"><p className="label">{t("create.scenes_title")}</p><Segmented label={t("create.scenes_a11y")} value={f.scenes} options={[{ id: "auto", label: t("create.scenes_auto") }, { id: "cartoon", label: t("create.scenes_illustrated") }, { id: "real", label: t("create.scenes_real") }]} onChange={(v) => set({ scenes: v })} /><p className="hint">{t("create.scenes_hint")}</p></div>}
                        {wm && <div className="opt"><p className="label">{t("create.wm_title")}</p>
                          <Segmented label={t("create.wm_title")} value={f.watermark ?? "saved"} options={[
                            ...(wm.forced ? [] : [{ id: "saved", label: t("create.wm_saved") }]),
                            ...wm.modes.map((m) => ({ id: m.id, label: t(m.id === "none" ? "create.wm_none" : m.id === "videomk" ? "create.wm_videomk" : m.available ? "create.wm_custom" : "create.wm_custom_locked"), disabled: !m.available })),
                          ]} onChange={(v) => set({ watermark: v === "saved" ? null : (v as Form["watermark"]) })} />
                          {wm.forced && <p className="hint">{t("create.wm_forced")}</p>}</div>}
                        {betterAvailable(c.dictation) && recordingSupported() && <div className="opt"><label className="opt-row" htmlFor="o-better"><span>{t("create.better_title")}</span><input id="o-better" type="checkbox" role="switch" className="vm-switch" checked={better} onChange={(e) => { setBetter(e.target.checked); setBetterPreferred(e.target.checked); }} /></label><p className="hint">{t("create.better_hint")}</p></div>}
                        {showUpgradeHint(c.dictation) && <p className="hint">{t("create.better_pro")}</p>}
                        <p className="hint">{t("create.options_note")}</p>
                      </div>
                    )}
                  </Popover>
                )}
                {working && <span className="tool-listening" role="status">{t("create.better_working")}</span>}
                {listening && <span className="tool-listening"><span className="live-dot" aria-hidden="true" />{t("create.dictating")}</span>}
              </div>

              <button type="submit" className={`btn btn-primary compose-go ${inactive ? "is-inactive" : ""}`} aria-disabled={inactive || undefined} aria-describedby="create-state" aria-label={t("create.cta_name")}>
                <span>{t("create.cta_word")}</span><span className="go-cost"><Icon name="bolt" size={16} />{credits}</span>
              </button>
              <span id="create-state" className="sr-only-vmk">{inactive ? t(why) : t("create.state_ready", { credits: costWords })}</span>
            </div>
            {caption && <p className="compose-balance">{caption}</p>}
          </div>
        )}
        <input ref={files} type="file" hidden tabIndex={-1} accept="image/*" multiple onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} />
        {vcaps && <input ref={videoInput} type="file" hidden tabIndex={-1} accept="video/mp4,video/quicktime,video/webm,.mp4,.m4v,.mov,.webm" onChange={(e) => { pickVideo(Array.from(e.target.files ?? [])); e.target.value = ""; }} />}
        {vcaps && canRecord && <input ref={recordInput} type="file" hidden tabIndex={-1} accept="video/*" capture="environment" onChange={(e) => { pickVideo(Array.from(e.target.files ?? [])); e.target.value = ""; }} />}
        {c.deck && <input ref={deckInput} type="file" hidden tabIndex={-1} accept={c.deck.formats.map((x) => (x === "pdf" ? ".pdf" : ".pptx")).join(",")} onChange={(e) => { const file = e.target.files?.[0]; if (file) void deck.begin(file); e.target.value = ""; }} />}
      </form>

      {/* the example chips are a first-run help: only while the field is empty and the account has no finished video */}
      {empty && finished === false && (
        <div className="chips compose-examples" role="group" aria-label={t("create.try_one")}>
          {EXAMPLES.map((k) => <button key={k} type="button" className="chip" onClick={() => { setHint(null); set({ text: t(k) }); area.current?.focus(); }}><Icon name="sparkle" size={15} />{t(k)}</button>)}
        </div>
      )}

      {clipFile && vcaps && <ClipSheet file={clipFile} caps={vcaps} t={t} onCancel={() => setClipFile(null)} onChooseAnother={() => { setClipFile(null); setTimeout(() => videoInput.current?.click(), 30); }} onAdd={addClip} />}
      {recent && vcaps && <RecentClipsSheet caps={vcaps} t={t} taken={clips.items.map((i) => i.id ?? "")} room={clipRoom} onUse={useRecent} onClose={() => setRecent(false)} />}
      {picker && <MediaPicker max={room} initialQuery={f.text} onClose={() => setPicker(false)} onUse={(photos: Photo[]) => { setPicker(false); setLibPicks((x) => [...x, ...photos.filter((p) => !x.some((y) => y.id === p.id)).map((p) => ({ id: p.id, thumb_url: p.thumb_url }))].slice(0, MAX_VIDEO_PHOTOS)); }} />}

      {(stage.k === "questions" || stage.k === "stop") && (
        <Sheet title={questionTitle} onClose={() => setStage({ k: "form" })}>
          {stage.k === "questions" ? (() => {
            const q = stage.questions[stage.i];
            return (
              <div className="mt-4">
                <div className="dots" aria-label={t("create.question_n", { n: stage.i + 1, total: stage.questions.length })}>{stage.questions.map((_, i) => <i key={i} className={i <= stage.i ? "on" : ""} />)}</div>
                <p className="q-title">{q.text}</p>
                <div className="chips mt-4">{q.options.map((o) => <button key={o.id} type="button" className="chip" onClick={() => void answer({ id: q.id, option: o.id })}>{o.label}</button>)}
                  <button type="button" className="chip" onClick={() => void answer({ id: q.id, skip: true })}><Icon name="sparkle" size={16} />{t("create.you_decide")}</button></div>
                {q.allow_other && (
                  <div className="mt-4 flex gap-2">
                    <input className="field" aria-label={t("create.type_answer")} placeholder={t("create.type_answer")} maxLength={200} value={other} onChange={(e) => setOther(e.target.value)} />
                    <button type="button" className="btn btn-tonal btn-sm shrink-0" disabled={!other.trim()} onClick={() => void answer({ id: q.id, text: other.trim() })}>{t("create.use_this")}</button>
                  </div>
                )}
                <div className="mt-6 flex justify-end"><button type="button" className="btn btn-line btn-sm" onClick={() => void finish(stage.answers)}>{t("create.make_it_now")}</button></div>
              </div>
            );
          })() : (
            <div className="mt-4 space-y-4">
              <p className={`notice ${stage.kind === "paused" ? "notice-warn" : "notice-info"}`} role="alert">{stage.message || (stage.kind === "paused" ? t("create.paused_fallback") : stage.kind === "blocked" ? t("create.blocked_fallback") : t("create.unsupported_fallback"))}</p>
              {stage.suggestion && <p className="muted">{stage.suggestion}</p>}
              <p className="caption">{t("create.nothing_charged")}</p>
              {stage.kind !== "paused" && <button type="button" className="btn btn-primary btn-block" onClick={() => { setStage({ k: "form" }); setTimeout(() => area.current?.focus(), 20); }}>{t("create.edit_request")}</button>}
            </div>
          )}
        </Sheet>
      )}
      <Shortcuts />
    </section>
  );
}
