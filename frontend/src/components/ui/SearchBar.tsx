import { Search } from "lucide-react";
import { useEffect, useState } from "react";

/** Debounced search input. */
export function SearchBar({ value, onChange, placeholder = "Search…" }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  const [draft, setDraft] = useState(value);

  useEffect(() => setDraft(value), [value]);
  useEffect(() => {
    const t = setTimeout(() => draft !== value && onChange(draft), 350);
    return () => clearTimeout(t);
  }, [draft, value, onChange]);

  return (
    <label className="relative block w-full sm:w-72">
      <span className="sr-only">{placeholder}</span>
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden />
      <input
        type="search"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        placeholder={placeholder}
        className="block w-full rounded-xl border-0 bg-white py-2.5 pl-9 pr-3 text-base shadow-sm ring-1 ring-inset ring-slate-200 transition-shadow duration-200 placeholder:text-slate-400 hover:ring-slate-300 focus:shadow-[0_0_0_4px_rgb(101_96_244/0.12)] focus:outline-none focus:ring-2 focus:ring-brand-500 sm:py-2 sm:text-sm"
      />
    </label>
  );
}
