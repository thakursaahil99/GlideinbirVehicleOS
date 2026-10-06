import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { ApiError } from "@/api/client";
import { organizationsApi, usersApi } from "@/api/resources";
import { Button } from "@/components/ui/Button";
import { Input, Textarea } from "@/components/ui/FormField";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/toast-context";
import type { Organization, User } from "@/types/api";

type Form = Record<string, string>;

/** Shared edit-form state: prefill on open, send only changed values, map field errors. */
function useEditForm(initial: Form | null, save: (changes: Form) => Promise<unknown>, onDone: () => void, success: string, keys: string[]) {
  const toast = useToast();
  const [form, setForm] = useState<Form>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  useEffect(() => {
    if (initial) {
      setForm(initial);
      setErrors({});
    }
  }, [initial]);
  const mutation = useMutation({
    mutationFn: () => {
      const changes: Form = {};
      for (const k of Object.keys(form)) if (form[k] !== (initial?.[k] ?? "")) changes[k] = form[k];
      return save(changes);
    },
    onSuccess: () => { toast.show(success, "success"); onDone(); },
    onError: (err) => {
      if (err instanceof ApiError) {
        setErrors(err.fieldErrors());
        toast.show(err.message, "error");
      }
    },
  });
  const bind = (k: string) => ({ value: form[k] ?? "", error: errors[k], onChange: (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value })) });
  void keys;
  return { bind, mutation };
}

export function EditUserModal({ user, onClose }: { user: User | null; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [initial, setInitial] = useState<Form | null>(null);
  useEffect(() => { setInitial(user ? { full_name: user.full_name, email: user.email, phone: user.phone ?? "", password: "" } : null); }, [user]);
  const { bind, mutation } = useEditForm(initial, (c) => usersApi.update(user!.id, c), () => {
    queryClient.invalidateQueries({ queryKey: ["users"] });
    onClose();
  }, "User updated.", []);

  return (
    <Modal open={Boolean(user)} title={user ? `Edit ${user.full_name}` : ""} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={mutation.isPending} onClick={() => mutation.mutate()}>Save changes</Button></>}>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); mutation.mutate(); }}>
        <Input label="Full name" {...bind("full_name")} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Input label="E-mail" type="email" autoComplete="off" {...bind("email")} />
          <Input label="Phone" type="tel" {...bind("phone")} />
        </div>
        <Input label="New password (optional)" type="password" autoComplete="new-password" {...bind("password")}
          hint="Leave blank to keep the current password. Setting one signs the user out everywhere." />
        <button type="submit" hidden />
      </form>
    </Modal>
  );
}

const AGENCY_FIELDS: [keyof Organization, string, boolean?][] = [
  ["name", "Agency name"], ["legal_name", "Legal name"], ["email", "Business e-mail"], ["phone", "Phone"],
  ["website", "Website"], ["gst_number", "GSTIN"], ["registration_number", "Registration no."],
  ["address", "Address"], ["city", "City"], ["state", "State"], ["country", "Country"], ["pincode", "Pincode"],
  ["description", "Description", true],
];

export function EditAgencyModal({ org, onClose }: { org: Organization | null; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [initial, setInitial] = useState<Form | null>(null);
  useEffect(() => {
    setInitial(org ? Object.fromEntries(AGENCY_FIELDS.map(([k]) => [k, String(org[k] ?? "")])) : null);
  }, [org]);
  const { bind, mutation } = useEditForm(initial, (c) => organizationsApi.update(org!.id, c as Partial<Organization>), () => {
    queryClient.invalidateQueries({ queryKey: ["orgs"] });
    onClose();
  }, "Agency updated.", []);

  return (
    <Modal open={Boolean(org)} title={org ? `Edit ${org.name}` : ""} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={mutation.isPending} onClick={() => mutation.mutate()}>Save changes</Button></>}>
      <form className="grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); mutation.mutate(); }}>
        {AGENCY_FIELDS.map(([k, label, long]) =>
          long ? <Textarea key={k} label={label} rows={3} wrapperClassName="sm:col-span-2" {...bind(k)} />
            : <Input key={k} label={label} wrapperClassName={k === "name" || k === "address" ? "sm:col-span-2" : undefined} {...bind(k)} />,
        )}
        <button type="submit" hidden />
      </form>
    </Modal>
  );
}
