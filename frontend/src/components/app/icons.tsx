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
  upload: <path {...P} d="M12 15V4m0 0L8 8m4-4 4 4M5 14v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4" />,
};
export function AIcon({ name, size = 20, className }: { name: string; size?: number; className?: string }) {
  if (EXTRA[name]) return <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" width={size} height={size} className={className}>{EXTRA[name]}</svg>;
  return <Icon name={name} size={size} className={className} />;
}
