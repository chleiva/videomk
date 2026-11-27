// Settings (docs/UX_2026_REDESIGN.md 4.4): grouped rows, no footnotes. Account, language and look, subtitles, photo dates and places, the watermark default, feedback and links,
// and Delete account (typed word, a recent sign-in, Apple's step). Logic in lib/settings.ts and lib/account.ts (tested).
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { PIcon } from "./PlayerIcons";
import { Dialog } from "./ui/Dialog";
import { Button } from "./ui/Button";
import { Sheet, Spinner, useToast } from "./ui";
import { getTokensIfAvailable, signOut } from "../lib/auth";
import { SITE_URL } from "../lib/config";
import { setLocale } from "../lib/i18n";
import type { Locale } from "../lib/i18n";
import { savedTheme, setTheme } from "../lib/theme";
import type { ThemeChoice } from "../lib/theme";
import { useLocale } from "../lib/useLocale";
import { CONFIRM_WORD, appleRevokeUrl, clearResume, confirmationOk, isFreshSignIn, readResume, RESUME_KEY, requestDeletion, signInAgain, wasConfirmed, wipeLocalData } from "../lib/account";
import type { AppleStep } from "../lib/account";
import { WM_POSITIONS, base64Of, loadWatermark, logoProblem, readPref, removeLogo, saveWatermark, uploadLogo, writePref } from "../lib/settings";
import type { PrefId, WmMode, WmPosition, WmView } from "../lib/settings";

// ---------------------------------------------------------------- small pieces
function Row({ icon, label, children, onClick, href, danger, info }: { icon?: string; label: string; children?: ReactNode; onClick?: () => void; href?: string; danger?: boolean; info?: ReactNode }) {
  const body = (
    <>
      {icon && <span className="row-icon" aria-hidden="true"><PIcon name={icon} size={20} /></span>}
      <span className="row-label">{label}</span>
      {info}
      <span className="row-end">{children}</span>
    </>
  );
  const cls = `srow${danger ? " srow-danger" : ""}`;
  if (href) return <a className={cls} href={href}>{body}<span className="row-go" aria-hidden="true"><PIcon name="chevron" size={18} /></span></a>;
  if (onClick) return <button type="button" className={cls} onClick={onClick}>{body}</button>;
  return <div className={cls}>{body}</div>;
}

function Switch({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label: string }) {
  return <button type="button" role="switch" aria-checked={on} aria-label={label} className="switch" onClick={() => onChange(!on)}><span /></button>;
}

function Segments<T extends string>({ value, options, onChange, label }: { value: T; options: { id: T; label: string }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div className="segs" role="radiogroup" aria-label={label}>
      {options.map((o) => <button key={o.id} type="button" role="radio" aria-checked={value === o.id} className="seg" onClick={() => onChange(o.id)}>{o.label}</button>)}
    </div>
  );
}

type Dlg = null | "type" | "signin" | "final" | "apple";

export default function SettingsPage() {
  const { t, locale } = useLocale();
  const toast = useToast();
  const [email, setEmail] = useState<string | null>(null);
  const [theme, setThemeState] = useState<ThemeChoice>("auto");
  const [prefs, setPrefs] = useState<Record<PrefId, boolean>>({ subtitles: true, photoDates: true, photoLocations: false });
  const [infoOpen, setInfoOpen] = useState(false);
  const [wm, setWm] = useState<WmView | null>(null);
  const [wmBusy, setWmBusy] = useState(false);
  const [dlg, setDlg] = useState<Dlg>(null);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<"" | "error" | "network">("");
  const [done, setDone] = useState<null | { manualApple: boolean }>(null);
  const file = useRef<HTMLInputElement>(null);
  const infoRef = useRef<HTMLDivElement>(null);
  const infoBtn = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    setThemeState(savedTheme());
    setPrefs({ subtitles: readPref("subtitles"), photoDates: readPref("photoDates"), photoLocations: readPref("photoLocations") });
    getTokensIfAvailable().then((tk) => {
      try { const p = JSON.parse(atob(String(tk?.id_token).split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))); setEmail(typeof p.email === "string" ? p.email : null); } catch { setEmail(null); }
    }).catch(() => {});
    loadWatermark().then(setWm);
    // back from signing in again for a deletion: one last confirmation, no typing
    const q = new URLSearchParams(location.search);
    if (q.get("delete") === "1") {
      const resumed = readResume(localStorage.getItem(RESUME_KEY)) !== null && wasConfirmed();
      history.replaceState({}, "", "/settings");
      clearResume();
      if (resumed) getTokensIfAvailable().then((tk) => { if (isFreshSignIn(tk?.id_token)) setDlg("final"); else setDlg("signin"); }).catch(() => {});
    }
  }, []);

  useEffect(() => {
    if (!infoOpen) return;
    const away = (e: MouseEvent) => { if (!infoRef.current?.contains(e.target as Node) && !infoBtn.current?.contains(e.target as Node)) setInfoOpen(false); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") { setInfoOpen(false); infoBtn.current?.focus(); } };
    document.addEventListener("mousedown", away); document.addEventListener("keydown", key);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", key); };
  }, [infoOpen]);

  const setPref = (id: PrefId, v: boolean) => { writePref(id, v); setPrefs((p) => ({ ...p, [id]: v })); };
  const pickTheme = (c: ThemeChoice) => { setTheme(c); setThemeState(c); };

  // ---- watermark
  const wmError = (message: string) => toast.show(message || t("settings.wm.save_failed"));
  async function chooseMode(mode: WmMode) {
    if (!wm || wmBusy || wm.settings.mode === mode) return;
    setWmBusy(true);
    const r = await saveWatermark({ mode, position: wm.settings.position });
    if (r.ok) setWm({ ...wm, settings: { ...wm.settings, mode } }); else wmError(r.message);
    setWmBusy(false);
  }
  async function choosePosition(position: WmPosition) {
    if (!wm || wmBusy || wm.settings.mode === "none") return;
    setWmBusy(true);
    const r = await saveWatermark({ mode: wm.settings.mode, position });
    if (r.ok) setWm({ ...wm, settings: { ...wm.settings, position } }); else wmError(r.message);
    setWmBusy(false);
  }
  async function pickLogo(f: File | undefined) {
    if (!wm || !f) return;
    const p = logoProblem(f, wm.logo.max_bytes, wm.logo.types);
    if (p) { toast.show(t(p === "big" ? "settings.wm.err_big" : p === "type" ? "settings.wm.err_type" : "settings.wm.err_empty")); return; }
    setWmBusy(true);
    const data = await new Promise<string | null>((resolve) => { const r = new FileReader(); r.onload = () => resolve(base64Of(String(r.result))); r.onerror = () => resolve(null); r.readAsDataURL(f); });
    if (!data) { toast.show(t("settings.wm.err_type")); setWmBusy(false); return; }
    const up = await uploadLogo(data);
    if (up.ok) {
      const next = await saveWatermark({ mode: "custom", position: wm.settings.position });
      setWm({ ...wm, settings: { ...wm.settings, mode: next.ok ? "custom" : wm.settings.mode, has_logo: true } });
    } else wmError(up.message);
    setWmBusy(false);
  }
  async function dropLogo() {
    if (!wm || wmBusy) return;
    setWmBusy(true);
    const r = await removeLogo();
    if (r.ok) setWm({ ...wm, settings: { ...wm.settings, has_logo: false, mode: wm.settings.mode === "custom" ? "videomk" : wm.settings.mode } }); else wmError(r.message);
    setWmBusy(false);
  }

  // ---- account
  const doSignOut = () => { signOut(); location.assign("/signin"); };
  const closeDlg = () => { if (busy) return; setDlg(null); setTyped(""); setProblem(""); };

  async function startDeletion() {
    setProblem("");
    const tk = await getTokensIfAvailable();
    if (!isFreshSignIn(tk?.id_token)) { setDlg("signin"); return; }
    await runDeletion();
  }

  async function runDeletion() {
    setBusy(true); setProblem("");
    const r = await requestDeletion();
    if (r.ok) { await afterAccepted(r.apple); return; }
    setBusy(false);
    if (r.kind === "reauth") setDlg("signin");
    else if (r.kind === "network") setProblem("network");
    else setProblem("error");
  }

  async function afterAccepted(apple: AppleStep) {
    if (apple === "revoke_available") { setBusy(false); setDlg("apple"); return; }
    finish(apple === "revoke_off");
  }

  function finish(manualApple: boolean) {
    wipeLocalData(); clearResume();
    setBusy(false); setDlg(null); setDone({ manualApple });
  }

  async function goApple() {
    setBusy(true);
    const url = await appleRevokeUrl();
    if (url) { wipeLocalData(); clearResume(); location.assign(url); return; }
    finish(true);   // Apple's page could not be prepared: the deletion stands, the person gets the manual steps
  }

  if (done) {
    return (
      <section className="page page-narrow settings">
        <div className="card done-card" role="status">
          <span className="done-mark"><PIcon name="check" size={28} /></span>
          <h1 className="h1" style={{ fontSize: "var(--fs-title2)" }}>{t("settings.deleted_title")}</h1>
          <p className="muted">{t("settings.deleted_body")}</p>
          {done.manualApple && <p className="muted">{t("settings.apple_manual")}</p>}
          <a className="btn btn-primary" href={SITE_URL}>{t("settings.home")}</a>
        </div>
      </section>
    );
  }

  const modeLabel = (m: WmMode, available: boolean) => m === "custom" && !available ? t("settings.wm.custom_locked") : t(`settings.wm.${m}`);
  const modes = wm?.modes ?? [];

  return (
    <section className="page page-narrow settings">
      <h1 className="h1">{t("settings.title")}</h1>

      <div className="sgroup">
        <Row icon="user" label={email ?? t("settings.signed_in")}><button type="button" className="slink" onClick={doSignOut}>{t("settings.sign_out")}</button></Row>
      </div>

      <div className="sgroup">
        <Row icon="globe" label={t("settings.language")}>
          <Segments<Locale> value={locale} label={t("settings.language")} onChange={(l) => setLocale(l)} options={[{ id: "en", label: "English" }, { id: "es", label: "Español" }]} />
        </Row>
        <Row icon="moon" label={t("settings.theme")}>
          <Segments<ThemeChoice> value={theme} label={t("settings.theme")} onChange={pickTheme} options={[{ id: "auto", label: t("settings.theme_auto") }, { id: "light", label: t("settings.theme_light") }, { id: "dark", label: t("settings.theme_dark") }]} />
        </Row>
        <Row icon="captions" label={t("settings.subtitles")}><Switch on={prefs.subtitles} onChange={(v) => setPref("subtitles", v)} label={t("settings.subtitles")} /></Row>
      </div>

      <div className="sgroup">
        <Row icon="image" label={t("settings.photo_dates")} info={
          <span className="info-anchor">
            <button ref={infoBtn} type="button" className="icon-btn info-btn" onClick={() => setInfoOpen((v) => !v)} aria-expanded={infoOpen} aria-controls="photos-info" aria-label={t("settings.info")} title={t("settings.info")}><PIcon name="help" size={18} /></button>
            {infoOpen && <div ref={infoRef} id="photos-info" className="popover" role="note">{t("settings.photos_info")}</div>}
          </span>
        }><Switch on={prefs.photoDates} onChange={(v) => setPref("photoDates", v)} label={t("settings.photo_dates")} /></Row>
        <Row icon="pin" label={t("settings.photo_locations")}><Switch on={prefs.photoLocations} onChange={(v) => setPref("photoLocations", v)} label={t("settings.photo_locations")} /></Row>
      </div>

      {wm && (
        <div className="sgroup" aria-busy={wmBusy || undefined}>
          <Row icon="drop" label={t("settings.watermark")}>
            <Segments<WmMode> value={wm.settings.mode} label={t("settings.watermark")} onChange={chooseMode}
              options={modes.filter((m) => m.id !== "none" || m.available).map((m) => ({ id: m.id, label: modeLabel(m.id, m.available) }))} />
          </Row>
          {wm.forced && <p className="srow-note">{t("settings.wm.forced")}</p>}
          {wm.settings.mode !== "none" && (
            <div className="srow srow-wide">
              <span className="row-label">{t("settings.wm.position")}</span>
              <div className="chips" role="radiogroup" aria-label={t("settings.wm.position")}>
                {WM_POSITIONS.map((p) => <button key={p} type="button" role="radio" aria-checked={wm.settings.position === p} className="chip" onClick={() => choosePosition(p)}>{t(`settings.wm.pos.${p}`)}</button>)}
              </div>
            </div>
          )}
          {wm.premium && (
            <div className="srow srow-wide">
              <input ref={file} type="file" className="sr-only-vmk" accept={wm.logo.types.join(",")} tabIndex={-1} aria-hidden="true" onChange={(e) => { void pickLogo(e.target.files?.[0]); e.target.value = ""; }} />
              <Button variant="tonal" small icon={<PIcon name="image" size={18} />} onClick={() => file.current?.click()} disabled={wmBusy}>{wm.settings.has_logo ? t("settings.wm.replace_logo") : t("settings.wm.choose_logo")}</Button>
              {wm.settings.has_logo && <Button variant="line" small onClick={dropLogo} disabled={wmBusy}>{t("settings.wm.remove_logo")}</Button>}
            </div>
          )}
        </div>
      )}

      <div className="sgroup">
        <Row icon="chat" label={t("settings.feedback")} href="/feedback?from=settings" />
        <Row icon="help" label={t("settings.support")} href={`${SITE_URL}/support`} />
        <Row icon="lock" label={t("settings.privacy")} href={`${SITE_URL}/privacy`} />
        <Row icon="check" label={t("settings.terms")} href={`${SITE_URL}/terms`} />
      </div>

      <div className="sgroup">
        <Row label={t("settings.delete")} danger onClick={() => { setTyped(""); setProblem(""); setDlg("type"); }} />
      </div>

      {dlg === "type" && (
        <Sheet title={t("settings.delete_title")} onClose={closeDlg} labelledBy="dialog-title">
          <div className="dialog-body">
            <p>{t("settings.delete_body")}</p>
            <label htmlFor="delete-word" className="label mt-4">{t("settings.delete_type")}</label>
            <input id="delete-word" className="field" value={typed} autoComplete="off" autoCapitalize="characters" spellCheck={false} placeholder={CONFIRM_WORD} data-autofocus="" onChange={(e) => setTyped(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && confirmationOk(typed) && !busy) void startDeletion(); }} />
            {problem && <p className="notice notice-bad mt-4" role="alert">{t(problem === "network" ? "settings.delete_network" : "settings.delete_error")}</p>}
          </div>
          <div className="dialog-actions">
            <Button variant="line" onClick={closeDlg}>{t("settings.cancel")}</Button>
            <Button variant="danger" busy={busy} disabled={!confirmationOk(typed)} onClick={() => void startDeletion()}>{t("settings.delete_confirm")}</Button>
          </div>
        </Sheet>
      )}
      {dlg === "signin" && (
        <Dialog title={t("settings.delete_signin_title")} confirmLabel={t("settings.delete_signin")} cancelLabel={t("settings.cancel")} onCancel={closeDlg} onConfirm={() => { void signInAgain(); }}>
          <p>{t("settings.delete_signin_body")}</p>
        </Dialog>
      )}
      {dlg === "final" && (
        <Dialog title={t("settings.delete_final_title")} danger busy={busy} confirmLabel={t("settings.delete_confirm")} cancelLabel={t("settings.cancel")} onCancel={closeDlg} onConfirm={() => { void runDeletion(); }}>
          <p>{t("settings.delete_final_body")}</p>
          {problem && <p className="notice notice-bad mt-4" role="alert">{t(problem === "network" ? "settings.delete_network" : "settings.delete_error")}</p>}
        </Dialog>
      )}
      {dlg === "apple" && (
        <Dialog title={t("settings.apple_title")} busy={busy} confirmLabel={t("settings.apple_go")} cancelLabel={t("settings.skip")} onCancel={() => finish(true)} onConfirm={() => { void goApple(); }}>
          <p>{t("settings.apple_body")}</p>
        </Dialog>
      )}
      {toast.node}
      {busy && dlg === null && <span className="sr-only-vmk" role="status"><Spinner /></span>}
    </section>
  );
}
