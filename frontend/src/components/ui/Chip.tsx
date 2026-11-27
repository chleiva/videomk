import type { ButtonHTMLAttributes, ReactNode } from "react";

export interface ChipProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "onChange"> {
  selected?: boolean;
  children: ReactNode;
}

/** A choice. Selected chips use aria-pressed (toggle) — put several in a `.chips` row. 2 to 4 choices per question: more belong in a menu or a sheet. */
export function Chip({ selected = false, className = "", children, type = "button", ...rest }: ChipProps) {
  return <button type={type} className={["chip", className].filter(Boolean).join(" ")} aria-pressed={selected} {...rest}>{children}</button>;
}
