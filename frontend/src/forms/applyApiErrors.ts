import type { FieldValues, Path, UseFormSetError } from "react-hook-form";

import { ApiError } from "@/api/client";

/**
 * Maps backend VALIDATION_ERROR details onto form fields. Returns the message
 * that should be shown globally (e.g. in a toast) when nothing field-level matched.
 */
export function applyApiErrors<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  fields: readonly string[],
): string | null {
  if (!(error instanceof ApiError)) return "Something went wrong. Please try again.";
  const fieldErrors = error.fieldErrors();
  let matched = false;
  for (const [field, message] of Object.entries(fieldErrors)) {
    if (fields.includes(field)) {
      setError(field as Path<T>, { type: "server", message });
      matched = true;
    }
  }
  return matched ? null : error.message;
}
