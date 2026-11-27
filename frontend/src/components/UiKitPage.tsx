// Developer preview of the shared UI kit (/ui-kit, noindex, not published to either site). Light/dark: use the switch in the rail, or ?theme=dark.
import { useState } from "react";
import { Button, Chip, Dialog, EmptyState, Icon, IconButton, Skeleton, Spinner, Tabs, Toast } from "./ui/index";

export default function UiKitPage() {
  const [tab, setTab] = useState("one");
  const [chips, setChips] = useState<string[]>(["a"]);
  const [dialog, setDialog] = useState(false);
  const toggle = (id: string) => setChips((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]));
  return (
    <div className="page" data-ui-kit>
      <h1 className="h1">UI kit</h1>
      <p className="caption">components/ui, tokens.css. One primary action per screen.</p>

      <section aria-labelledby="k-buttons" style={{ marginTop: "var(--space-8)" }}>
        <h2 id="k-buttons" className="h2">Buttons</h2>
        <div className="chips" style={{ marginTop: "var(--space-3)" }}>
          <Button>Primary</Button><Button variant="tonal">Tonal</Button><Button variant="line">Line</Button><Button variant="danger">Danger</Button>
          <Button busy>Busy</Button><Button disabled>Disabled</Button><Button small>Small</Button>
          <IconButton label="Share"><Icon name="share" /></IconButton><IconButton label="More"><Icon name="dots" /></IconButton>
          <Spinner />
        </div>
      </section>

      <section aria-labelledby="k-chips" style={{ marginTop: "var(--space-8)" }}>
        <h2 id="k-chips" className="h2">Chips and tabs</h2>
        <div className="chips" style={{ marginTop: "var(--space-3)" }}>
          {[["a", "YouTube"], ["b", "TikTok"], ["c", "LinkedIn"]].map(([id, label]) => <Chip key={id} selected={chips.includes(id)} onClick={() => toggle(id)}>{label}</Chip>)}
        </div>
        <div style={{ marginTop: "var(--space-4)" }}>
          <Tabs label="Example" value={tab} onChange={setTab} items={[{ id: "one", label: "Videos" }, { id: "two", label: "Media" }, { id: "three", label: "Credits" }]} />
        </div>
      </section>

      <section aria-labelledby="k-feedback" style={{ marginTop: "var(--space-8)" }}>
        <h2 id="k-feedback" className="h2">Skeleton, empty state, dialog, toasts</h2>
        <div style={{ display: "grid", gap: "var(--space-2)", marginTop: "var(--space-3)", maxWidth: "24rem" }} aria-busy="true">
          <Skeleton height="10rem" radius="var(--radius-video)" /><Skeleton width="70%" /><Skeleton width="40%" />
        </div>
        <div style={{ marginTop: "var(--space-4)" }}><EmptyState title="No videos yet" body="Describe an idea and it shows up here." action={<Button>New video</Button>} /></div>
        <div style={{ marginTop: "var(--space-4)" }}><Button variant="line" onClick={() => setDialog(true)}>Open dialog</Button></div>
        {dialog && <Dialog title="Delete this video?" confirmLabel="Delete" cancelLabel="Keep" onConfirm={() => setDialog(false)} onCancel={() => setDialog(false)} danger>It cannot be undone.</Dialog>}
      </section>
      <div style={{ marginTop: "var(--space-8)", display: "grid", gap: "var(--space-2)", maxWidth: "28rem" }}>
        <div className="toast toast-info" role="status" style={{ animation: "none" }}>Saved to your videos</div>
        <div className="toast toast-success" role="status" style={{ animation: "none" }}>Video ready</div>
        <div className="toast toast-error" role="alert" style={{ animation: "none" }}>Could not reach the server</div>
        <span hidden><Toast>unused</Toast></span>
      </div>
    </div>
  );
}
