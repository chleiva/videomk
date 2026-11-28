// Icons package B needs that the shared set (components/ui.tsx) does not have yet; everything else falls through to it. Same stroke style (1.8, round).
import type { ReactNode } from "react";
import { Icon } from "../ui";

const P = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round" } as const;
const EXTRA: Record<string, ReactNode> = {
  search: <path {...P} d="M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-4-4" />,
  image: <path {...P} d="M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zM4 16l4.5-4.5 4 4 3-3L20 17M9 9h.01" />,
  sliders: <path {...P} d="M4 7h9M17 7h3M4 17h3M11 17h9M15 4v6M9 14v6" />,
  trash: <path {...P} d="M5 7h14M10 7V5h4v2M7 7l1 12h8l1-12M10 11v5M14 11v5" />,
  folder: <path {...P} d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />,
  warning: <path {...P} d="M12 4 3 19h18zM12 10v4M12 16.5v.5" />,
  stop: <rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" />,
  chevdown: <path {...P} d="m6 9 6 6 6-6" />,
  left: <path {...P} d="M15 5l-7 7 7 7" />,
  right: <path {...P} d="m9 5 7 7-7 7" />,
  collection: <path {...P} d="M4 8h16M6 5h12M5 11h14v8H5z" />,
  sparkle: <path {...P} d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z" />,
  retry: <path {...P} d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7" />,
  newvideo: <path {...P} d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9zM18.5 15.5v5M16 18h5" />,
  addphoto: <path {...P} d="M13 5H6a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-7M4 16l4-4 4 4 2.5-2.5L19 18M18.5 3v6M15.5 6h6M9 9.5h.01" />,
  folderplus: <path {...P} d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM12 10.5v5M9.5 13h5" />,
  lock: <path {...P} d="M7 11V8a5 5 0 0 1 10 0v3M6 11h12a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1z" />,
  clock: <path {...P} d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2" />,
  "shape-wide": <rect {...P} x="3" y="6.5" width="18" height="11" rx="2.5" />,
  "shape-tall": <rect {...P} x="7.5" y="3" width="9" height="18" rx="2.5" />,
  "shape-square": <rect {...P} x="5" y="5" width="14" height="14" rx="2.5" />,
  "shape-portrait": <rect {...P} x="6" y="4" width="12" height="16" rx="2.5" />,
  people: <path {...P} d="M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM3.5 19a5.5 5.5 0 0 1 11 0M16 5.2a3 3 0 0 1 0 5.6M17.5 14a5.5 5.5 0 0 1 3 5" />,
  volume: <path {...P} d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5zM15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11" />,
  volumeoff: <path {...P} d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5zM16 9.5l5 5M21 9.5l-5 5" />,
  videoadd: <path {...P} d="M13 6H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h7a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2zM15 11l5-3v8l-5-3M8 10l3 2-3 2z" />,
  upload: <path {...P} d="M12 15V4m0 0L8 8m4-4 4 4M5 14v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4" />,
};
export function AIcon({ name, size = 20, className }: { name: string; size?: number; className?: string }) {
  if (EXTRA[name]) return <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" width={size} height={size} className={className}>{EXTRA[name]}</svg>;
  return <Icon name={name} size={size} className={className} />;
}

/** The glyph of a format: its shape (landscape, portrait, tall, square) from an id such as "16:9". */
export function shapeGlyph(aspect: string): string {
  const [w, h] = aspect.split(":").map(Number), r = w > 0 && h > 0 ? w / h : 16 / 9;
  return r > 1.2 ? "shape-wide" : r > 0.95 ? "shape-square" : r > 0.7 ? "shape-portrait" : "shape-tall";
}
