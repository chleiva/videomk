// Icons of the watch page, settings and sign-in (24x24, stroke 1.8, round), drawn inline like components/ui.tsx. Decorative: every control that uses one carries its own accessible name.
import type { ReactNode } from "react";

const S = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round" } as const;
const F = { fill: "currentColor", stroke: "none" } as const;

export const PATHS: Record<string, ReactNode> = {
  play: <path {...F} d="M8 5.2v13.6a.6.6 0 0 0 .92.5l10.6-6.8a.6.6 0 0 0 0-1L8.92 4.7A.6.6 0 0 0 8 5.2Z" />,
  pause: <path {...F} d="M7 5h3.2v14H7zM13.8 5H17v14h-3.2z" />,
  replay: <path {...S} d="M4 12a8 8 0 1 0 2.6-5.9M4 4v4.5h4.5" />,
  volume: <path {...S} d="M4 9.5h3.5L12 5.5v13l-4.5-4H4zM15.5 9a4.2 4.2 0 0 1 0 6M18 6.5a8 8 0 0 1 0 11" />,
  mute: <path {...S} d="M4 9.5h3.5L12 5.5v13l-4.5-4H4zM16 9.5l4.5 5M20.5 9.5l-4.5 5" />,
  fullscreen: <path {...S} d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" />,
  exitFullscreen: <path {...S} d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5" />,
  pip: <path {...S} d="M4 6.5A1.5 1.5 0 0 1 5.5 5h13A1.5 1.5 0 0 1 20 6.5v11a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5zM12.5 12.5h5.5v4h-5.5z" />,
  captions: <path {...S} d="M4 6.5A1.5 1.5 0 0 1 5.5 5h13A1.5 1.5 0 0 1 20 6.5v11a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5zM9.8 10.2a2.4 2.4 0 1 0 0 3.6M16.3 10.2a2.4 2.4 0 1 0 0 3.6" />,
  share: <path {...S} d="M12 15V3.5m0 0L7.8 7.7M12 3.5l4.2 4.2M5.5 12v6.5a1.5 1.5 0 0 0 1.5 1.5h10a1.5 1.5 0 0 0 1.5-1.5V12" />,
  download: <path {...S} d="M12 4v11m0 0-4.2-4.2M12 15l4.2-4.2M5 19.5h14" />,
  sliders: <path {...S} d="M5 7h9m4 0h1M5 17h1m4 0h9M14 4.5v5M10 14.5v5" />,
  info: <path {...S} d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 11v5.2M12 7.9h.01" />,
  more: <path {...F} d="M6 10.5a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3zM12 10.5a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3zM18 10.5a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3z" />,
  back: <path {...S} d="M14.5 5.5 8 12l6.5 6.5" />,
  plus: <path {...S} d="M12 5v14M5 12h14" />,
  copy: <path {...S} d="M9 9h9.5A1.5 1.5 0 0 1 20 10.5V19a1.5 1.5 0 0 1-1.5 1.5H10A1.5 1.5 0 0 1 8.5 19V9.5M4 15V5.5A1.5 1.5 0 0 1 5.5 4H15" />,
  flag: <path {...S} d="M6 21V4.5M6 5h11l-2.2 3.5L17 12H6" />,
  chat: <path {...S} d="M5 5.5A2.5 2.5 0 0 1 7.5 3h9A2.5 2.5 0 0 1 19 5.5v8a2.5 2.5 0 0 1-2.5 2.5H11l-4 3.5V16h-.5A2.5 2.5 0 0 1 4 13.5" />,
  check: <path {...S} d="m5 12.5 4.5 4.5L19 7.5" />,
  close: <path {...S} d="m6 6 12 12M18 6 6 18" />,
  chevron: <path {...S} d="m9 6 6 6-6 6" />,
  edit: <path {...S} d="M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4" />,
  user: <path {...S} d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4.5 20a7.5 7.5 0 0 1 15 0" />,
  globe: <path {...S} d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM3.5 12h17M12 3c2.5 2.4 3.8 5.4 3.8 9S14.5 18.6 12 21c-2.5-2.4-3.8-5.4-3.8-9S9.5 5.4 12 3z" />,
  moon: <path {...S} d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z" />,
  image: <path {...S} d="M4 6.5A1.5 1.5 0 0 1 5.5 5h13A1.5 1.5 0 0 1 20 6.5v11a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5zM4.5 16l4.2-4.2a1.2 1.2 0 0 1 1.7 0L15 16.4M14 14.5l1.4-1.4a1.2 1.2 0 0 1 1.7 0l2.4 2.4M15.5 9.5h.01" />,
  pin: <path {...S} d="M12 21s6.5-5.6 6.5-11a6.5 6.5 0 0 0-13 0C5.5 15.4 12 21 12 21zM12 12.2a2.2 2.2 0 1 0 0-4.4 2.2 2.2 0 0 0 0 4.4z" />,
  bolt: <path {...F} d="M13.5 2 5 13.5h5.5L9.5 22 19 9.5h-5.7z" />,
  drop: <path {...S} d="M12 3.5s6 6.3 6 10.5a6 6 0 0 1-12 0c0-4.2 6-10.5 6-10.5z" />,
  help: <path {...S} d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM9.6 9.6a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1.1.9-1.1 1.8M12 16.6h.01" />,
  lock: <path {...S} d="M6.5 11h11a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1h-11a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1zM8.5 11V8a3.5 3.5 0 0 1 7 0v3" />,
};

export function PIcon({ name, size = 22, className }: { name: keyof typeof PATHS | string; size?: number; className?: string }) {
  return <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" width={size} height={size} className={className}>{PATHS[name]}</svg>;
}

/** The videomk mark (Sparklet Trio, docs/brand/final/favicon.svg) as inline SVG so the sign-in page needs no request: a play triangle that emits sparks, on the brand gradient. */
export function BrandMark({ size = 64 }: { size?: number }) {
  return <img src="/favicon.svg" width={size} height={size} alt="" aria-hidden="true" className="brand-tile" style={{ width: size, height: size }} />;
}
