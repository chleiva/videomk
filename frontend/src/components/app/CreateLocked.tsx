// Create for an account that cannot make a video right now (docs/PLANS.md section 3: a Free account whose free creation is off, app-only, used up or paused, with no
// credit to spend). Never an empty or broken form: the server's own sentence, the plan's name, and the showcase of videos made with VideoMK (`GET /gallery`).
// There is no buy button: nothing can be bought yet (`can_upgrade` is false everywhere).
import "../../styles/app-b.css";
import { useEffect, useState } from "react";
import { AIcon as Icon } from "./icons";
import Shortcuts from "./Shortcuts";
import { getGallery } from "../../lib/plan";
import type { CreateLock, GalleryVideo } from "../../lib/plan";
import { formatDuration } from "../../lib/videos";
import { useLocale } from "../../lib/useLocale";

type T = (key: string, params?: Record<string, string | number>) => string;

function ShowcaseTile({ v, t }: { v: GalleryVideo; t: T }) {
  const [playing, setPlaying] = useState(false);
  const dur = formatDuration(v.seconds);
  const name = v.title || t("gen.untitled");
  return (
    <li className="show-tile" data-aspect={v.aspect ?? "16:9"}>
      <span className="show-pic" style={{ aspectRatio: (v.aspect ?? "16:9").replace(":", " / ") }}>
        {playing
          ? <video src={v.video_url} poster={v.poster_url ?? undefined} controls autoPlay playsInline aria-label={name} />
          : <button type="button" className="show-play" aria-label={t("gen.watch", { title: name })} onClick={() => setPlaying(true)}>
              {v.poster_url && <img src={v.poster_url} alt="" loading="lazy" decoding="async" />}
              <span className="show-glyph" aria-hidden="true"><Icon name="play" size={22} /></span>
              {dur && <span className="duration">{dur}</span>}
            </button>}
      </span>
      {v.title && <p className="vtile-title">{v.title}</p>}
    </li>
  );
}

/** The locked card and the showcase, without the network (drawn on its own in the tests). */
export function LockedView({ lock, plan, videos, t }: { lock: CreateLock; plan: string | null; videos: GalleryVideo[]; t: T }) {
  return (
    <>
      <div className="composer-card create-locked" role="status">
        <span className="locked-badge" aria-hidden="true"><Icon name="lock" size={22} /></span>
        <p className="locked-msg">{lock.message || t("create.locked_fallback")}</p>
        <p className="locked-plan">{plan ? t("create.locked_plan", { plan }) : t("create.locked_soon")}</p>
      </div>
      {videos.length > 0 && (
        <div className="showcase">
          <p className="eyebrow" id="showcase-title">{t("create.showcase")}</p>
          <ul className="show-grid" aria-labelledby="showcase-title">{videos.map((v) => <ShowcaseTile key={v.id} v={v} t={t} />)}</ul>
        </div>
      )}
    </>
  );
}

export default function CreateLocked({ lock, plan }: { lock: CreateLock; plan: string | null }) {
  const { t } = useLocale();
  const [videos, setVideos] = useState<GalleryVideo[]>([]);
  useEffect(() => { let alive = true; void getGallery().then((v) => alive && setVideos(v)); return () => { alive = false; }; }, []);
  return (
    <section className="page compose is-gated">
      <div className="compose-aura" aria-hidden="true" />
      <div className="compose-head"><h1 className="compose-title">{t("create.heading")}</h1></div>
      <LockedView lock={lock} plan={plan} videos={videos} t={t} />
      <Shortcuts />
    </section>
  );
}
