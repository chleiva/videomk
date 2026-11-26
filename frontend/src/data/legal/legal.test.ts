import { describe, expect, it } from "vitest";
import { getDelete } from "./delete";
import { getPrivacy } from "./privacy";
import { getSupport } from "./support";
import { getTerms } from "./terms";
import type { LegalContent, Section } from "./types";

const pages: Record<string, (l: "en" | "es") => LegalContent> = { privacy: getPrivacy, terms: getTerms, support: getSupport, delete: getDelete };
const nums = (s: Section) => (JSON.stringify(s).match(/\d+/g) ?? []).sort().join(",");
// the unit of a number in running text may differ ("2 días" / "2 days"), so compare the digits only

describe.each(Object.entries(pages))("legal page %s", (_name, get) => {
	const en = get("en"), es = get("es");
	it("has the same structure in both languages", () => {
		expect(es.sections.length).toBe(en.sections.length);
		expect(es.glance.length).toBe(en.glance.length);
		es.sections.forEach((s, i) => {
			const e = en.sections[i];
			expect(s.paras?.length ?? 0, `paras of section ${i + 1}`).toBe(e.paras?.length ?? 0);
			expect(s.bullets?.length ?? 0, `bullets of section ${i + 1}`).toBe(e.bullets?.length ?? 0);
			expect(s.after?.length ?? 0, `after of section ${i + 1}`).toBe(e.after?.length ?? 0);
			expect(s.table?.head.length, `table head of section ${i + 1}`).toBe(e.table?.head.length);
			expect(s.table?.rows.length, `table rows of section ${i + 1}`).toBe(e.table?.rows.length);
			s.table?.rows.forEach((r, ri) => expect(r.length).toBe(e.table!.rows[ri].length));
		});
	});
	it("keeps every number (periods, limits, section references)", () => {
		es.sections.forEach((s, i) => expect(nums(s), `section ${i + 1}`).toBe(nums(en.sections[i])));
		expect(es.glance.join(" ").match(/\d+/g)?.sort()).toEqual(en.glance.join(" ").match(/\d+/g)?.sort());
	});
	it("uses the neutral Spanish glossary", () => {
		const text = JSON.stringify(es).toLowerCase();
		for (const w of ["ordenador", "computadora", "móvil", "celular", "vídeo"]) expect(text).not.toContain(w);
	});
});
