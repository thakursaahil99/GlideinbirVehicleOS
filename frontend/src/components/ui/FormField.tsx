import { forwardRef, useId, type InputHTMLAttributes, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";

import { cn } from "@/utils/format";

const control =
  "block w-full rounded-xl border-0 bg-white px-3.5 py-2.5 text-base text-slate-900 shadow-sm ring-1 ring-inset transition-shadow duration-200 placeholder:text-slate-400 hover:ring-slate-400 focus:shadow-[0_0_0_4px_rgb(101_96_244/0.12)] focus:ring-2 focus:ring-inset focus:ring-brand-500 focus:outline-none disabled:bg-slate-100 sm:py-2 sm:text-sm";

interface FieldShellProps {
  id: string;
  label?: string;
  error?: string;
  hint?: string;
  children: React.ReactNode;
  className?: string;
}

function FieldShell({ id, label, error, hint, children, className }: FieldShellProps) {
  return (
    <div className={className}>
      {label && (
        <label htmlFor={id} className="mb-1 block text-sm font-medium text-slate-700">
          {label}
        </label>
      )}
      {children}
      {error ? (
        <p id={`${id}-error`} className="mt-1 animate-fade-in text-xs text-rose-600" role="alert">
          {error}
        </p>
      ) : (
        hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>
      )}
    </div>
  );
}

type InputProps = InputHTMLAttributes<HTMLInputElement> & { label?: string; error?: string; hint?: string; wrapperClassName?: string };

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, error, hint, className, wrapperClassName, id, ...rest },
  ref,
) {
  const autoId = useId();
  const inputId = id ?? autoId;
  return (
    <FieldShell id={inputId} label={label} error={error} hint={hint} className={wrapperClassName}>
      <input
        ref={ref}
        id={inputId}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? `${inputId}-error` : undefined}
        className={cn(control, error ? "ring-rose-400" : "ring-slate-300", className)}
        {...rest}
      />
    </FieldShell>
  );
});

type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & { label?: string; error?: string; wrapperClassName?: string };

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { label, error, className, wrapperClassName, id, ...rest },
  ref,
) {
  const autoId = useId();
  const inputId = id ?? autoId;
  return (
    <FieldShell id={inputId} label={label} error={error} className={wrapperClassName}>
      <textarea
        ref={ref}
        id={inputId}
        rows={3}
        aria-invalid={Boolean(error)}
        className={cn(control, error ? "ring-rose-400" : "ring-slate-300", className)}
        {...rest}
      />
    </FieldShell>
  );
});

type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & { label?: string; error?: string; wrapperClassName?: string };

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, error, className, wrapperClassName, id, children, ...rest },
  ref,
) {
  const autoId = useId();
  const inputId = id ?? autoId;
  return (
    <FieldShell id={inputId} label={label} error={error} className={wrapperClassName}>
      <select ref={ref} id={inputId} className={cn(control, "pr-8", error ? "ring-rose-400" : "ring-slate-300", className)} {...rest}>
        {children}
      </select>
    </FieldShell>
  );
});
