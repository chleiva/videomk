// Wires lib/shortcuts.ts to the document and shows the `?` sheet. One per page. "/" asks the page to focus its search (event vmk:search; the page answers with preventDefault).
import { useEffect, useMemo, useState } from "react";
import { Sheet } from "../ui";
import { APP_PATHS } from "../../lib/links";
import { SHORTCUT_ROWS, createShortcuts } from "../../lib/shortcuts";
import type { Dest } from "../../lib/shortcuts";
import { useLocale } from "../../lib/useLocale";

const PATH: Record<Dest, string> = { videos: APP_PATHS.videos, media: APP_PATHS.media, credits: APP_PATHS.credits, new: "/new" };

export default function Shortcuts() {
  const { t } = useLocale();
  const [help, setHelp] = useState(false);
  const handler = useMemo(() => createShortcuts({
    go: (d) => { if (location.pathname !== PATH[d]) location.assign(PATH[d]); },
    search: () => { const e = new CustomEvent("vmk:search", { cancelable: true }); window.dispatchEvent(e); return e.defaultPrevented; },
    help: () => setHelp(true),
  }), []);
  useEffect(() => {
    const on = (e: KeyboardEvent) => { if (handler({ key: e.key, ctrlKey: e.ctrlKey, metaKey: e.metaKey, altKey: e.altKey, target: e.target as HTMLElement | null })) e.preventDefault(); };
    document.addEventListener("keydown", on);
    return () => document.removeEventListener("keydown", on);
  }, [handler]);
  if (!help) return null;
  return (
    <Sheet title={t("gen.shortcuts_title")} onClose={() => setHelp(false)}>
      <dl className="kbd-list">
        {SHORTCUT_ROWS.map((r) => (
          <div key={r.key} className="kbd-row"><dt>{r.keys.map((k, i) => <span key={k + i}>{i > 0 && <span className="kbd-then">{" "}</span>}<kbd>{k}</kbd></span>)}</dt><dd>{t(r.key)}</dd></div>
        ))}
      </dl>
    </Sheet>
  );
}
