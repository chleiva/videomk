// The sample videos on the home page (public/samples/). Rules (docs/WEB_REDESIGN_2026.md section 7):
//  - every video is a REAL VideoMK output made through the real pipeline (nothing mocked); the files here are short cuts (<= 30 s) with their sound;
//  - `prompt` is shown with the video ONLY when it is the real prompt that produced it (an excerpt taken word for word is allowed); `null` means "title only";
//  - no personal photos or identifiable people (the Majorca family videos were left out on purpose);
//  - features that are not live for everybody yet (animated backgrounds, cartoon scenes) are not shown.
// To add a sample: encode a cut (H.264, <= 4.5 MB for the hero, <= 2.5 MB for the others), a WebP poster (<= 70 KB hero, <= 35 KB others), add a row here.
export type Aspect = "wide" | "tall" | "square" | "portrait";
export interface Sample {
  id: string;
  file: string;        // /samples/<id>.mp4
  poster: string;      // /samples/<id>.webp
  width: number;
  height: number;
  seconds: number;
  aspect: Aspect;
  lang: "en" | "es";   // narration language
  title: Record<"en" | "es", string>;   // what the video is about (the plan title, in the narration language; the other language gets a translation of it)
  prompt: string | null;               // verbatim excerpt of the real prompt, or null
  promptShort?: string;                // a shorter word-for-word excerpt of `prompt` (shown over the hero video)
  description: Record<"en" | "es", string>;
}

export const SAMPLES: Sample[] = [
  {
    id: "forest", file: "/samples/forest.mp4", poster: "/samples/forest.webp", width: 1280, height: 720, seconds: 28, aspect: "wide", lang: "en",
    title: { en: "How a forest breathes and why forests matter", es: "Cómo respira un bosque y por qué importa" },
    promptShort: "A calm explainer about how a forest breathes and why forests matter",
    prompt: "A calm explainer about how a forest breathes and why forests matter: how trees take in carbon dioxide and release oxygen, how roots and soil store carbon, and how a forest keeps the air and water clean. Please use real video footage of forests wherever it fits. Warm, gentle, wonder-filled tone.",
    description: { en: "Footage, a counting statistic and an animated list, narrated and captioned.", es: "Imágenes de video, una estadística animada y una lista, con narración y subtítulos." },
  },
  {
    id: "bees", file: "/samples/bees.mp4", poster: "/samples/bees.webp", width: 1280, height: 720, seconds: 30, aspect: "wide", lang: "en",
    title: { en: "How bees turn nectar into honey", es: "Cómo convierten las abejas el néctar en miel" },
    prompt: null,
    description: { en: "Stock footage and photos, a step-by-step diagram and a closing line.", es: "Imágenes y fotos con licencia, un diagrama paso a paso y una frase final." },
  },
  {
    id: "focus", file: "/samples/focus.mp4", poster: "/samples/focus.webp", width: 540, height: 960, seconds: 30, aspect: "tall", lang: "en",
    title: { en: "3 quick tips to focus while studying", es: "3 consejos rápidos para concentrarte al estudiar" },
    prompt: null,
    description: { en: "Made for TikTok, Reels and Shorts: 30 seconds, vertical, big type.", es: "Pensado para TikTok, Reels y Shorts: 30 segundos, vertical, letra grande." },
  },
  {
    id: "jobs", file: "/samples/jobs.mp4", poster: "/samples/jobs.webp", width: 720, height: 720, seconds: 28, aspect: "square", lang: "en",
    title: { en: "Your job in 10 years: what AI really changes", es: "Tu trabajo dentro de 10 años: qué cambia de verdad la IA" },
    prompt: null,
    description: { en: "Charts, a comparison and a quote, researched from current sources.", es: "Gráficos, una comparación y una cita, con investigación de fuentes actuales." },
  },
  {
    id: "agents", file: "/samples/agents.mp4", poster: "/samples/agents.webp", width: 640, height: 800, seconds: 30, aspect: "portrait", lang: "en",
    title: { en: "AI agents and jobs: where 2026 leads by 2031", es: "Agentes de IA y empleo: hacia dónde va 2026 hasta 2031" },
    prompt: null,
    description: { en: "Big numbers, a ring chart and a ranked list for the Instagram feed.", es: "Cifras grandes, un gráfico circular y un ranking para el feed de Instagram." },
  },
  {
    id: "pulpo", file: "/samples/pulpo.mp4", poster: "/samples/pulpo.webp", width: 1280, height: 720, seconds: 15, aspect: "wide", lang: "es",
    title: { en: "The octopus: eight arms and a lot of brain", es: "El dato curioso del pulpo: ocho brazos y mucho cerebro" },
    prompt: null,
    description: { en: "A 15-second fact in Spanish, with kinetic type.", es: "Un dato de 15 segundos en español, con texto animado." },
  },
];

/** The video shown big at the top of the page (its prompt sits under it). */
export const HERO = SAMPLES[0];
/** The grid under the hero; the Spanish page puts the Spanish-narrated video first. */
export function galleryFor(locale: "en" | "es"): Sample[] {
  const rest = SAMPLES.slice(1);
  return [...rest.filter((s) => s.lang === locale), ...rest.filter((s) => s.lang !== locale)];
}
export const ASPECT_KEY: Record<Aspect, string> = { wide: "gallery.aspect_wide", tall: "gallery.aspect_tall", square: "gallery.aspect_square", portrait: "gallery.aspect_portrait" };
