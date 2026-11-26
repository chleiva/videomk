export type Locale = "en" | "es";
export interface Section { title: string; paras?: string[]; bullets?: string[]; table?: { head: string[]; rows: string[][] }; after?: string[] }
export interface LegalContent { title: string; intro: string; glance: string[]; sections: Section[] }
