import { cn } from "@/utils/format";

/** Project credit shown in every layout. */
export function BuiltBy({ className }: { className?: string }) {
  return (
    <p className={cn("text-xs text-slate-500", className)}>
      Glideinbir · Vehicle Operating System · Built by <span className="font-semibold text-slate-700">Sahil Thakur</span>
    </p>
  );
}
