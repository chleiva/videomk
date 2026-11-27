// "Organise your photos?" after a big upload (30 or more photos; docs/MEDIA_LIBRARY.md Smart collections): what we would make, one button, or everything in one collection.
import { useEffect, useState } from "react";
import { Sheet, Spinner } from "../ui";
import { organizeApply, organizePreview, setOrganizePref } from "../../lib/library";
import type { OrganizePreview } from "../../lib/library";
import { useLocale } from "../../lib/useLocale";

export default function OrganizeSheet({ since, onClose, onDone }: { since?: string; onClose: () => void; onDone: () => void }) {
  const { t } = useLocale();
  const [prev, setPrev] = useState<OrganizePreview | null | "error">(null);
  const [busy, setBusy] = useState(false);
  const [one, setOne] = useState(false);
  const [name, setName] = useState("");
  const [always, setAlways] = useState(false);
  const [err, setErr] = useState(false);
  useEffect(() => { let alive = true; void organizePreview(since).then((p) => alive && setPrev(p ?? "error")); return () => { alive = false; }; }, [since]);

  async function go(mode: "auto" | "single") {
    setBusy(true); setErr(false);
    if (always) await setOrganizePref("always");
    const ok = await organizeApply(mode, since, mode === "single" ? name.trim() || t("media.new_collection") : undefined);
    setBusy(false);
    if (ok) onDone(); else setErr(true);
  }
  const nothing = prev !== null && prev !== "error" && prev.groups.length === 0;
  return (
    <Sheet title={t("library.organize_title")} onClose={onClose}>
      <div className="mt-4 space-y-4">
        {prev === null && <p className="muted" role="status"><Spinner /> {t("library.organize_working")}</p>}
        {prev === "error" && <p className="notice notice-warn" role="alert">{t("library.organize_error")}</p>}
        {nothing && <p className="muted">{t("library.organize_nothing")}</p>}
        {prev && prev !== "error" && !nothing && !one && (
          <>
            <p className="muted">{t("library.organize_body")}</p>
            <ul className="org-groups">{prev.groups.slice(0, 6).map((g) => <li key={g.name}><span>{g.name}</span><span className="muted">{g.count}{g.existing ? ` ${t("library.organize_adds")}` : ""}</span></li>)}
              {prev.groups.length > 6 && <li className="muted">{t("library.organize_groups", { n: prev.groups.length })}</li>}</ul>
          </>
        )}
        {one && (<><p className="muted">{t("library.organize_name")}</p><input className="field" autoFocus data-autofocus maxLength={40} aria-label={t("media.collection_name")} placeholder={t("media.collection_name")} value={name} onChange={(e) => setName(e.target.value)} /></>)}
        {err && <p className="notice notice-warn" role="alert">{t("library.organize_error")}</p>}
        {prev && prev !== "error" && !nothing && (
          <>
            {!one && <label className="opt-row"><span>{t("library.organize_always")}</span><input type="checkbox" role="switch" className="vm-switch" checked={always} onChange={(e) => setAlways(e.target.checked)} /></label>}
            <div className="dialog-actions">
              <button type="button" className="btn btn-line btn-sm" onClick={() => (one ? setOne(false) : onClose())} disabled={busy}>{one ? t("media.cancel") : t("library.organize_later")}</button>
              {!one && <button type="button" className="btn btn-line btn-sm" onClick={() => setOne(true)} disabled={busy}>{t("library.organize_one")}</button>}
              <button type="button" className="btn btn-primary btn-sm" data-autofocus={one ? undefined : ""} disabled={busy || (one && !name.trim())} onClick={() => void go(one ? "single" : "auto")}>{busy ? <Spinner /> : one ? t("media.create") : t("library.organize_yes")}</button>
            </div>
          </>
        )}
        {(prev === "error" || nothing) && <div className="dialog-actions"><button type="button" className="btn btn-primary btn-sm" onClick={onClose}>{t("create.done")}</button></div>}
      </div>
    </Sheet>
  );
}
