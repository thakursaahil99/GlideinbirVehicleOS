import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/utils/format";

type Variant = "primary" | "secondary" | "danger" | "ghost" | "success";
type Size = "sm" | "md";

const variants: Record<Variant, string> = {
  primary:
    "bg-gradient-to-b from-brand-500 to-brand-700 text-white shadow-[var(--shadow-glow)] ring-1 ring-inset ring-white/10 hover:brightness-110 focus-visible:ring-brand-500",
  secondary: "bg-white text-slate-700 shadow-sm ring-1 ring-inset ring-slate-200 hover:bg-slate-50 hover:ring-slate-300 focus-visible:ring-brand-500",
  danger: "bg-gradient-to-b from-rose-500 to-rose-700 text-white shadow-[0_8px_20px_-6px_rgb(225_29_72/0.45)] hover:brightness-110 focus-visible:ring-rose-500",
  success:
    "bg-gradient-to-b from-emerald-500 to-emerald-700 text-white shadow-[0_8px_20px_-6px_rgb(5_150_105/0.45)] hover:brightness-110 focus-visible:ring-emerald-500",
  ghost: "text-slate-600 hover:bg-slate-100 focus-visible:ring-brand-500",
};

const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-xs",
  md: "h-10 px-4 text-sm",
};

/** Variants that get the light sweep on hover. */
const shiny: Variant[] = ["primary", "danger", "success"];

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

export function Button({ variant = "primary", size = "md", loading, disabled, className, children, ...rest }: ButtonProps) {
  return (
    <button
      type="button"
      disabled={disabled || loading}
      className={cn(
        "group/btn relative inline-flex items-center justify-center gap-2 overflow-hidden rounded-xl font-medium transition-all duration-200",
        "active:scale-[0.97] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2",
        "disabled:cursor-not-allowed disabled:opacity-60 disabled:active:scale-100",
        variants[variant],
        sizes[size],
        className,
      )}
      {...rest}
    >
      {shiny.includes(variant) && (
        <span
          aria-hidden
          className="pointer-events-none absolute inset-y-0 -left-full w-1/2 -skew-x-12 bg-gradient-to-r from-transparent via-white/25 to-transparent transition-[left] duration-700 ease-out group-hover/btn:left-[150%]"
        />
      )}
      {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}
