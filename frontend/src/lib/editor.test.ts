import { describe, expect, it } from "vitest";
import { bulletsToText, chartToText, diagramToText, diffOps, emptyScene, stable, textToBullets, textToChart, textToDiagram, textToTimeline, timelineToText, validateBeat } from "./editor";
import type { Beat, Meta } from "./editor";

const beat = (id: string, text = "one two three four five six", scene: Beat["scene"] = { type: "title", props: { title: id } }): Beat => ({ id, narration: text, scene });
const meta: Meta = { title: "T", theme: "midnight", mood: "calm", voice: "" };
const server = [beat("aaaaaaaa"), beat("bbbbbbbb"), beat("cccccccc"), beat("dddddddd")];

describe("diffOps", () => {
  it("emits nothing when nothing changed", () => {
    expect(diffOps(server, structuredClone(server), meta, { ...meta })).toEqual([]);
  });

  it("emits only the changed field of the changed beat", () => {
    const local = structuredClone(server);
    local[1].narration = "a completely different narration for this beat";
    expect(diffOps(server, local, meta, meta)).toEqual([{ op: "set_narration", id: "bbbbbbbb", text: "a completely different narration for this beat" }]);
  });

  it("detects scene prop changes (deep) and meta changes", () => {
    const local = structuredClone(server);
    local[0].scene.props.title = "New";
    const ops = diffOps(server, local, meta, { ...meta, theme: "paper", voice: "Puck" });
    expect(ops).toEqual([
      { op: "set_meta", theme: "paper" }, { op: "set_voice", voice: "Puck" },
      { op: "set_scene", id: "aaaaaaaa", type: "title", props: { title: "New" } },
    ]);
  });

  it("deletes, inserts (after real ids and after other inserts) and reorders so that the simulated server list equals the local list", () => {
    const n1: Beat = { ...beat("tmp1"), ref: "n1" };
    const n2: Beat = { ...beat("tmp2"), ref: "n2" };
    const local = [server[3], server[0], n1, n2, server[2]]; // delete b; move d first; insert n1,n2 after a
    const ops = diffOps(server, local, meta, meta);
    // replay the ops with the server's semantics
    let cur = server.map((b) => b.id);
    const refs: Record<string, string> = {};
    const res = (x: string | null) => (x && x.startsWith("ref:") ? refs[x] : x);
    for (const o of ops) {
      if (o.op === "delete") cur = cur.filter((x) => x !== o.id);
      if (o.op === "insert") { const id = `new-${o.ref}`; refs[`ref:${o.ref}`] = id; const at = o.after === null ? 0 : cur.indexOf(res(o.after)!) + 1; cur.splice(at, 0, id); }
      if (o.op === "move") { const id = res(o.id)!; cur.splice(cur.indexOf(id), 1); cur.splice(o.to, 0, id); }
    }
    expect(cur).toEqual(["dddddddd", "aaaaaaaa", "new-n1", "new-n2", "cccccccc"]);
    expect(ops.filter((o) => o.op === "insert").map((o) => o.after)).toEqual(["aaaaaaaa", "ref:n1"].map((x) => x));
  });

  it("emits pick_image for a newly chosen candidate, but not when the query changed in the same edit", () => {
    const img = (pick: string | null, q = "rainbow"): Beat => ({ id: "iiiiiiii", narration: "one two three four five six", scene: { type: "image", props: { image_query: q } }, pick });
    expect(diffOps([img(null)], [img("openverse:o1")], meta, meta)).toEqual([{ op: "pick_image", id: "iiiiiiii", candidate: "openverse:o1" }]);
    const both = diffOps([img(null)], [img("openverse:o1", "waterfall")], meta, meta).map((o) => o.op);
    expect(both).toEqual(["set_scene"]);
  });
});

describe("text formats", () => {
  it("diagram text round-trips and builds nodes from names", () => {
    const d = textToDiagram("Sunlight -> Raindrop\nRaindrop -> Your eye : bent light\nLonely");
    expect(d.nodes.map((n) => n.label)).toEqual(["Sunlight", "Raindrop", "Your eye", "Lonely"]);
    expect(d.edges).toEqual([["n1", "n2"], ["n2", "n3", "bent light"]]);
    expect(textToDiagram(diagramToText(d))).toEqual(d);
    expect(textToDiagram("A -> B -> C : go").edges).toEqual([["n1", "n2"], ["n2", "n3", "go"]]);
    expect(textToDiagram("A -> A").edges).toEqual([]);
  });

  it("chart and timeline text round-trip and ignore junk lines", () => {
    const c = textToChart("Red: 42\nGreen: 41,5\nno value here\nBad: x");
    expect(c).toEqual({ labels: ["Red", "Green"], values: [42, 415] });
    expect(textToChart(chartToText({ labels: ["a", "b"], values: [1, 2.5] }))).toEqual({ labels: ["a", "b"], values: [1, 2.5] });
    const t = textToTimeline("1915 | Einstein publishes\nNo date line");
    expect(t).toEqual([{ date: "1915", label: "Einstein publishes" }, { date: "", label: "No date line" }]);
    expect(textToTimeline(timelineToText(t))).toEqual(t);
    expect(textToBullets("a\n\n b \nc\nd\ne\nf")).toHaveLength(5);
    expect(bulletsToText(["x", "y"])).toBe("x\ny");
  });
});

describe("validateBeat", () => {
  const limits = { min_words: 6, max_words: 70 };
  it("mirrors the server's rules", () => {
    expect(validateBeat(beat("a", "too short"), limits)[0]).toMatch(/at least 6/);
    expect(validateBeat(beat("a", "word ".repeat(80)), limits)[0]).toMatch(/limited to 70/);
    expect(validateBeat({ ...beat("a"), scene: emptyScene("bullets") }, limits)).toContain("Add at least two bullet points.");
    expect(validateBeat({ ...beat("a"), scene: emptyScene("diagram") }, limits)[0]).toMatch(/two steps/);
    expect(validateBeat(beat("a"), limits)).toEqual([]);
  });
  it("stable() ignores key order", () => {
    expect(stable({ a: 1, b: [1, { c: 2, d: 3 }] })).toBe(stable({ b: [1, { d: 3, c: 2 }], a: 1 }));
  });
});
