export interface SkeletonProps { width?: string; height?: string; radius?: string; className?: string }

/** A placeholder block while content loads. Decorative (aria-hidden): announce loading with the container's aria-busy or a status line instead. Shimmer stops with reduced motion. */
export function Skeleton({ width = "100%", height = "1rem", radius, className = "" }: SkeletonProps) {
  return <span aria-hidden="true" className={["skeleton", className].filter(Boolean).join(" ")} style={{ width, height, borderRadius: radius }} />;
}
