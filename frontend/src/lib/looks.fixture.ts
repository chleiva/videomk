// The `looks` object of GET .../capabilities exactly as docs/CREATE_API.md "Video look (chosen and enforced)" documents it (QA does not serve it yet):
// the tests of the picker are written against this. The pictures are one-pixel stand-ins.
const JPEG = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA=";
const PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=";
const ALL = ["16:9", "9:16", "1:1", "4:5"];
const tile = (o: Record<string, unknown>): Record<string, any> => ({ preview: JPEG, available: true, allowed: true, requires_plan: null, with_photos: true, with_deck: true, min_seconds: 15, aspects: ALL, best_aspects: ALL, cast: false, extras: [], ...o });
const member = (id: string, name: string, role: string, kind: "person" | "animal", topic: string) => ({ id, name, role, kind, topic, thumbnail: PNG });

export const LOOKS_FIXTURE = {
  look: { param: "look", default: "auto", enforced: true, options: [
    tile({ id: "auto", label: "Auto", note: "We pick one look that suits your topic." }),
    tile({ id: "real", label: "Real", note: "Photos and video footage." }),
    tile({ id: "whiteboard", label: "Whiteboard", note: "Drawn by hand as it is explained.", with_photos: false, with_deck: false, best_aspects: ["16:9", "1:1"] }),
    tile({ id: "cartoon", label: "Cartoon", note: "Cartoon characters explain it.", with_photos: false, with_deck: false, best_aspects: ["16:9", "1:1", "4:5"], cast: true,
      extras: [{ id: "board", label: "Hand-drawn board", note: "The characters explain on a board that is drawn as they speak.", available: true }] }),
  ] },
  cast: { param: "cast", default: "auto", min: 1, max: 3, available: true,
    auto: { id: "auto", label: "Auto", note: "We pick characters that suit the topic." },
    conversation: { from: 2, min_seconds: 20, note: "Pick 2 or 3 and they talk it through together." },
    members: [
      member("ines", "Inés", "Teacher", "person", "Learning"), member("david", "David", "Engineer", "person", "How things work"),
      member("priya", "Priya", "Doctor", "person", "Health"), member("mateo", "Mateo", "Chef", "person", "Food"),
      member("fox", "Fox", "Guide for children", "animal", "For children"), member("bear", "Bear", "Storyteller", "animal", "Stories"),
      member("owl", "Owl", "Professor", "animal", "Science"), member("cat", "Cat", "Sceptic", "animal", "Everyday life"),
      member("dog", "Dog", "Coach", "animal", "Sport"), member("rabbit", "Rabbit", "Explorer", "animal", "Nature"),
    ] },
};
/** The same body with one tile changed (by id). */
export function looksWith(id: string, patch: Record<string, unknown>) {
  return { ...LOOKS_FIXTURE, look: { ...LOOKS_FIXTURE.look, options: LOOKS_FIXTURE.look.options.map((o) => (o.id === id ? { ...o, ...patch } : o)) } };
}
