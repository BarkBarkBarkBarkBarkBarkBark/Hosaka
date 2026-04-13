import { cn } from "@/lib/utils"

type BadgeVariant = "default" | "accent" | "success" | "muted"

interface BadgeProps {
  children: React.ReactNode
  variant?: BadgeVariant
  className?: string
}

const variants: Record<BadgeVariant, string> = {
  default:
    "bg-slate-800 text-slate-300 border border-slate-700",
  accent:
    "bg-blue-500/10 text-blue-400 border border-blue-500/20",
  success:
    "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
  muted:
    "bg-slate-900 text-slate-500 border border-slate-800",
}

export default function Badge({
  children,
  variant = "default",
  className,
}: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-xs font-mono uppercase tracking-widest rounded-full px-3 py-1",
        variants[variant],
        className
      )}
    >
      {children}
    </span>
  )
}
