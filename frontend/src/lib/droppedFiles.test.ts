import { describe, expect, it } from "vitest";
import { filesFromDrop } from "./droppedFiles";

const f = (n: string) => new File([""], n);
const fileEntry = (n: string) => ({ isFile: true, isDirectory: false, file: (ok: (x: File) => void) => ok(f(n)) });
const dirEntry = (children: any[], batch = 2) => ({ isFile: false, isDirectory: true, createReader: () => { let i = 0; return { readEntries: (ok: (e: any[]) => void) => { const part = children.slice(i, i + batch); i += batch; ok(part); } }; } });
const item = (e: any) => ({ webkitGetAsEntry: () => e });

describe("filesFromDrop", () => {
  it("walks dropped folders (in batches, nested) and plain files", async () => {
    const dt = { files: [] as unknown as FileList, items: [item(dirEntry([fileEntry("a.jpg"), fileEntry("b.jpg"), dirEntry([fileEntry("c.jpg")]), fileEntry("d.jpg")])), item(fileEntry("e.jpg"))] as unknown as DataTransferItemList };
    expect((await filesFromDrop(dt)).map((x) => x.name)).toEqual(["a.jpg", "b.jpg", "c.jpg", "d.jpg", "e.jpg"]);
  });
  it("is bounded", async () => {
    const many = Array.from({ length: 50 }, (_, i) => fileEntry(`p${i}.jpg`));
    const dt = { files: [] as unknown as FileList, items: [item(dirEntry(many, 10))] as unknown as DataTransferItemList };
    expect((await filesFromDrop(dt, 20)).length).toBe(20);
  });
  it("falls back to dt.files when the browser has no entry API", async () => {
    const dt = { files: [f("x.jpg"), f("y.jpg")] as unknown as FileList, items: [{}] as unknown as DataTransferItemList };
    expect((await filesFromDrop(dt)).map((x) => x.name)).toEqual(["x.jpg", "y.jpg"]);
    expect(await filesFromDrop(null)).toEqual([]);
  });
});
