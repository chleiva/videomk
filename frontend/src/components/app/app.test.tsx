import { describe, expect, it } from "vitest";
import { renderToStaticMarkup as html } from "react-dom/server";
import MediaGrid, { photoLabel } from "./MediaGrid";
import { Menu, Segmented } from "./Menu";
import UploadBanner from "./UploadBanner";
import { UploadQueue } from "../../lib/upload";
import type { QueueSummary } from "../../lib/upload";
import { translate } from "../../lib/i18n";
import { lengthLabel } from "../../lib/create";
import type { Photo } from "../../lib/library";

const photo = (id: string, taken: string, place?: string): Photo => ({ id, taken, added: taken, place, w: 1, h: 1, bytes: 1, thumb_url: `https://t/${id}.jpg`, collections: [] });
const sel = (ids: string[]) => ({ ids, anchor: ids[0] ?? null });
const noop = () => {};

describe("My media grid", () => {
  const items = [photo("a", "2026-07-14T10:00:00", "Phuket, Thailand"), photo("b", "2026-07-02T09:00:00"), photo("c", "2026-05-20T09:00:00")];
  it("groups the timeline by month under real headings and gives every tile its date and place as its name", () => {
    const m = html(<MediaGrid items={items} grouped selection={sel([])} onSelection={noop} max={100} />);
    expect(m).toContain("July 2026"); expect(m).toContain("May 2026");
    expect(m).toContain('aria-label="July 14, 2026, Phuket, Thailand"');
    expect(m).toContain('role="list"');
  });
  it("search results are one flat group without headings", () => {
    expect(html(<MediaGrid items={items} grouped={false} selection={sel([])} onSelection={noop} max={100} />)).not.toContain("<h2");
  });
  it("selected tiles say so and expose pressed state; every tile has a labelled checkbox", () => {
    const m = html(<MediaGrid items={items} grouped selection={sel(["a"])} onSelection={noop} max={100} />);
    expect(m).toContain("is-on");
    expect(m).toContain("selected");
    expect((m.match(/mtile-check/g) ?? []).length).toBeGreaterThanOrEqual(3);
    expect(m).toContain('aria-pressed="true"');
  });
  it("picker mode has no separate checkbox, only the tile and a tick on the selected one", () => {
    const m = html(<MediaGrid items={items} grouped={false} selection={sel(["b"])} onSelection={noop} selectOnly max={100} />);
    expect(m).not.toContain("mtile-check");
    expect(m).toContain("mtile-tick");
  });
  it("tiles are lazy and decorative images; the date label is localised", () => {
    const m = html(<MediaGrid items={items} grouped selection={sel([])} onSelection={noop} max={100} />);
    expect(m).toContain('loading="lazy"'); expect(m).toContain('alt=""');
    expect(photoLabel(items[0], "es")).toContain("julio");
  });
});

describe("menus and segmented controls", () => {
  it("a closed menu is a labelled button that announces its popup", () => {
    const m = html(<Menu label="Length" trigger={<span>1 min</span>} items={[{ id: "1", label: "1 min", checked: true }]} onPick={noop} />);
    expect(m).toContain('aria-haspopup="menu"'); expect(m).toContain('aria-expanded="false"'); expect(m).toContain('aria-label="Length"');
    expect(m).not.toContain('role="menu"');
  });
  it("segmented: radio group with one checked option and disabled ones really disabled", () => {
    const m = html(<Segmented label="Watermark" value="none" options={[{ id: "none", label: "None" }, { id: "custom", label: "Your logo (Pro)", disabled: true }]} onChange={noop} />);
    expect(m).toContain('role="radiogroup"'); expect(m).toContain('aria-label="Watermark"');
    expect(m).toContain('aria-checked="true"'); expect(m).toContain("disabled");
  });
});

describe("upload banner", () => {
  const empty = (over: Partial<QueueSummary> = {}): QueueSummary => ({ total: 0, finished: 0, done: 0, duplicates: 0, noSpace: 0, unsupported: 0, failed: 0, cancelled: 0, active: 0, pct: 0, bytes: 0, bytesDone: 0, paused: false, storageFull: false, running: false, ...over });
  const q = new UploadQueue({ prepare: async () => null, requestSlot: async () => ({ ok: false, kind: "error" }), post: async () => ({ ok: true }), sleep: async () => {} });
  it("shows nothing without uploads", () => expect(html(<UploadBanner queue={q} summary={empty()} onDismiss={noop} />)).toBe(""));
  it("one line with progress while uploading, a progressbar and Pause / Cancel", () => {
    const m = html(<UploadBanner queue={q} summary={empty({ total: 10, finished: 3, done: 3, active: 2, pct: 30, bytes: 5e6, bytesDone: 1.5e6, running: true })} onDismiss={noop} />);
    expect(m).toContain("Uploading 4 of 10"); expect(m).toContain('role="progressbar"'); expect(m).toContain("Pause"); expect(m).toContain("Cancel");
  });
  it("when finished: the outcome, what needs attention, Retry only if something failed", () => {
    const m = html(<UploadBanner queue={q} summary={empty({ total: 5, finished: 5, done: 3, duplicates: 1, failed: 1 })} onDismiss={noop} />);
    expect(m).toContain("3 photos added"); expect(m).toContain("already in your library"); expect(m).toContain("Try again"); expect(m).toContain("Dismiss");
    expect(html(<UploadBanner queue={q} summary={empty({ total: 2, finished: 2, done: 2 })} onDismiss={noop} />)).not.toContain("Try again");
  });
});

// The owner's rule: minimal text. The Create surface (before the person types anything) stays within its budget of the words the screen itself adds
// (docs/UX_2026_REDESIGN.md text budgets; the placeholder and the three example prompts are help for an empty box and disappear as soon as there is text).
describe("text budget", () => {
  const words = (s: string) => s.trim().split(/\s+/).filter(Boolean).length;
  for (const locale of ["en", "es"] as const) {
    it(`Create surface (${locale}) is at most 14 words`, () => {
      const t = (k: string, p?: Record<string, string | number>) => translate(k, locale, p);
      const surface = [t("create.heading"), t("create.other_platform"), lengthLabel(1), t("create.look_auto"), t("create.cta", { n: 1 }), t("create.left", { n: 11 })];
      expect(surface.reduce((n, s) => n + words(s), 0)).toBeLessThanOrEqual(14);
    });
    it(`Options (${locale}) stays within 40 words of fixed text`, () => {
      const t = (k: string) => translate(k, locale);
      const fixed = ["create.options", "create.done", "create.format", "create.resolution", "create.subtitles", "create.narration", "create.lang_auto", "create.wm_title", "create.wm_saved", "create.wm_none", "create.wm_videomk", "create.wm_custom_locked", "create.options_note"].map(t);
      expect(fixed.reduce((n, s) => n + words(s), 0)).toBeLessThanOrEqual(40);
    });
    it(`Videos (${locale}) shows at most 6 fixed words`, () => {
      const t = (k: string) => translate(k, locale);
      expect(["gen.nav_label", "gen.search", "gen.new_video"].map(t).reduce((n, s) => n + words(s), 0)).toBeLessThanOrEqual(6);
    });
  }
});
