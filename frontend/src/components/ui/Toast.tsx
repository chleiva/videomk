import type { ReactNode } from "react";

export type ToastTone = "info" | "success" | "error";
export interface ToastProps { tone?: ToastTone; children: ReactNode }

/** One message at the bottom of the screen. Errors are announced assertively (role=alert), everything else politely (role=status). Use `useToast()` from ../ui to show and hide it. */
export function Toast({ tone = "info", children }: ToastProps) {
  return (
    <div className="toast-host">
      <div className={`toast toast-${tone}`} role={tone === "error" ? "alert" : "status"} aria-live={tone === "error" ? "assertive" : "polite"}>{children}</div>
    </div>
  );
}
