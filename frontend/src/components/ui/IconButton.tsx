import type { ButtonHTMLAttributes, ReactNode } from "react";

export interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "aria-label" | "children"> {
  /** Required: icon-only controls have no visible text, so the accessible name is mandatory (translate it). */
  label: string;
  children: ReactNode;
  pressed?: boolean;
}

export function IconButton({ label, children, pressed, className = "", type = "button", ...rest }: IconButtonProps) {
  return (
    <button type={type} className={["icon-btn", className].filter(Boolean).join(" ")} aria-label={label} title={label} aria-pressed={pressed} {...rest}>
      {children}
    </button>
  );
}
