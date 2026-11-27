import type { ReactNode } from "react";
import { Sheet } from "../ui";
import { Button } from "./Button";

export interface DialogProps {
  title: string;
  /** One or two sentences. Longer content belongs on a page. */
  children?: ReactNode;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  /** Destructive confirmations use the danger style and never take the initial focus. */
  danger?: boolean;
  busy?: boolean;
}

/** A confirmation: title, a sentence, a cancel and a confirm button. Focus is trapped, Escape and the scrim cancel (Sheet). */
export function Dialog({ title, children, confirmLabel, cancelLabel, onConfirm, onCancel, danger, busy }: DialogProps) {
  return (
    <Sheet title={title} onClose={onCancel} labelledBy="dialog-title">
      {children && <div className="dialog-body">{children}</div>}
      <div className="dialog-actions">
        <Button variant="line" onClick={onCancel} data-autofocus={danger ? "" : undefined}>{cancelLabel}</Button>
        <Button variant={danger ? "danger" : "primary"} onClick={onConfirm} busy={busy} data-autofocus={danger ? undefined : ""}>{confirmLabel}</Button>
      </div>
    </Sheet>
  );
}
