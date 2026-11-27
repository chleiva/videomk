// Files from a drop or paste, folders included (Chrome, Safari and Firefox expose a dropped folder through webkitGetAsEntry). Pictures only; sidecar files are filtered later by
// lib/upload.pictureFiles. Bounded: at most `limit` files and a depth of 6 folders, so dropping a whole disk cannot hang the tab.
interface Entry { isFile: boolean; isDirectory: boolean; file?: (ok: (f: File) => void, err: (e: unknown) => void) => void; createReader?: () => { readEntries: (ok: (e: Entry[]) => void, err: (e: unknown) => void) => void } }

async function walk(e: Entry, out: File[], limit: number, depth: number): Promise<void> {
  if (out.length >= limit || depth > 6) return;
  if (e.isFile && e.file) { try { out.push(await new Promise<File>((ok, err) => e.file!(ok, err))); } catch { /* unreadable file: skip */ } return; }
  if (e.isDirectory && e.createReader) {
    const reader = e.createReader();
    for (;;) {   // readEntries returns batches until it returns an empty list
      const batch = await new Promise<Entry[]>((ok) => reader.readEntries(ok, () => ok([])));
      if (!batch.length) break;
      for (const child of batch) { if (out.length >= limit) return; await walk(child, out, limit, depth + 1); }
    }
  }
}

export async function filesFromDrop(dt: Pick<DataTransfer, "items" | "files"> | null | undefined, limit = 1000): Promise<File[]> {
  if (!dt) return [];
  const items = dt.items ? Array.from(dt.items) : [];
  const entries = items.map((i) => (typeof (i as any).webkitGetAsEntry === "function" ? ((i as any).webkitGetAsEntry() as Entry | null) : null)).filter(Boolean) as Entry[];
  if (!entries.length) return Array.from(dt.files ?? []).slice(0, limit);
  const out: File[] = [];
  for (const e of entries) await walk(e, out, limit, 0);
  return out;
}
