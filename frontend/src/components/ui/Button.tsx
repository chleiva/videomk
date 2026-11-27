import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Spinner } from "../ui";

export type ButtonVariant = "primary" | "tonal" | "line" | "danger";
export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  small?: boolean;
  block?: boolean;
  /** Shows a spinner, sets aria-busy and blocks clicks while true. */
  busy?: boolean;
  icon?: ReactNode;
}

/** The ONE primary action per screen is `variant="primary"` (gradient). Everything else is tonal or line. Targets are 44 px (tokens `--min-touch`). */
export function Button({ variant = "primary", small, block, busy, icon, className = "", children, disabled, type = "button", ...rest }: ButtonProps) {
  const cls = ["btn", `btn-${variant}`, small ? "btn-sm" : "", block ? "btn-block" : "", className].filter(Boolean).join(" ");
  return (
    <button type={type} className={cls} disabled={disabled || busy} aria-busy={busy || undefined} {...rest}>
      {busy ? <Spinner /> : icon}
      {children}
    </button>
  );
}
