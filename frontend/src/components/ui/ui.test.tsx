import { describe, expect, it } from "vitest";
import { renderToStaticMarkup as html } from "react-dom/server";
import { Button, Chip, Dialog, IconButton, Skeleton, Tabs, Toast, nextTab } from "./index";
import { Icon } from "../ui";

describe("ui kit: accessible names and states", () => {
  it("Button: variant classes, busy blocks and announces", () => {
    expect(html(<Button>Go</Button>)).toContain("btn btn-primary");
    const busy = html(<Button busy variant="tonal">Go</Button>);
    expect(busy).toContain("btn-tonal");
    expect(busy).toContain('aria-busy="true"');
    expect(busy).toContain("disabled");
    expect(html(<Button type="submit">x</Button>)).toContain('type="submit"');
    expect(html(<Button>x</Button>)).toContain('type="button"');
  });
  it("IconButton: the label is the accessible name", () => {
    const m = html(<IconButton label="Close"><Icon name="close" /></IconButton>);
    expect(m).toContain('aria-label="Close"');
    expect(m).toContain('title="Close"');
    expect(m).toContain('aria-hidden="true"');
  });
  it("Chip: aria-pressed follows selected", () => {
    expect(html(<Chip selected>A</Chip>)).toContain('aria-pressed="true"');
    expect(html(<Chip>A</Chip>)).toContain('aria-pressed="false"');
  });
  it("Toast: errors are alerts, the rest are polite status", () => {
    expect(html(<Toast tone="error">x</Toast>)).toContain('role="alert"');
    expect(html(<Toast>x</Toast>)).toContain('role="status"');
    expect(html(<Toast tone="success">x</Toast>)).toContain("toast-success");
  });
  it("Skeleton is decorative", () => {
    expect(html(<Skeleton />)).toContain('aria-hidden="true"');
  });
  it("Dialog: a labelled modal with both buttons; danger moves the initial focus to cancel", () => {
    const m = html(<Dialog title="Delete?" confirmLabel="Delete" cancelLabel="Keep" onConfirm={() => {}} onCancel={() => {}} danger>Cannot be undone.</Dialog>);
    expect(m).toContain('role="dialog"');
    expect(m).toContain('aria-modal="true"');
    expect(m).toContain('aria-labelledby="dialog-title"');
    expect(m).toContain("btn-danger");
    expect(m.indexOf("data-autofocus")).toBeLessThan(m.indexOf("btn-danger"));   // the first autofocus belongs to the cancel button
  });
  it("Tabs: tablist, one selected tab, roving tabindex", () => {
    const m = html(<Tabs label="View" value="b" onChange={() => {}} items={[{ id: "a", label: "A" }, { id: "b", label: "B" }]} />);
    expect(m).toContain('role="tablist"');
    expect(m).toContain('aria-label="View"');
    expect(m.match(/aria-selected="true"/g)?.length).toBe(1);
    expect(m).toContain('tabindex="0"');
    expect(m).toContain('tabindex="-1"');
  });
  it("nextTab: arrows wrap, Home and End jump, other keys do nothing", () => {
    const ids = ["a", "b", "c"];
    expect(nextTab(ids, "a", "ArrowRight")).toBe("b");
    expect(nextTab(ids, "c", "ArrowRight")).toBe("a");
    expect(nextTab(ids, "a", "ArrowLeft")).toBe("c");
    expect(nextTab(ids, "b", "Home")).toBe("a");
    expect(nextTab(ids, "b", "End")).toBe("c");
    expect(nextTab(ids, "b", "x")).toBeNull();
    expect(nextTab(ids, "zz", "ArrowRight")).toBeNull();
  });
});
