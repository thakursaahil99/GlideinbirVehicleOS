import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { ApiError } from "@/api/client";
import { organizationsApi, usersApi, type UserCreateInput } from "@/api/resources";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/FormField";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/toast-context";
import type { Role } from "@/types/api";
import { AGENCY_ROLES, ROLE_LABELS } from "@/utils/format";

const EMPTY: UserCreateInput = { email: "", full_name: "", phone: "", role: "CUSTOMER", organization: "", password: "" };

/** Super Admin: create an account of any role. Agency roles join the chosen agency. */
export function CreateUserModal({ open, onClose, defaultOrganization }: { open: boolean; onClose: () => void; defaultOrganization?: string }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<UserCreateInput>(EMPTY);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const needsAgency = AGENCY_ROLES.includes(form.role as Role);

  useEffect(() => {
    if (!open) return;
    setErrors({});
    setForm(defaultOrganization ? { ...EMPTY, role: "AGENCY_STAFF", organization: defaultOrganization } : EMPTY);
  }, [open, defaultOrganization]);

  const agencies = useQuery({
    queryKey: ["orgs", "picker"],
    queryFn: () => organizationsApi.list({ page_size: 100, ordering: "name" }),
    enabled: open && needsAgency,
    staleTime: 60_000,
  });

  const save = useMutation({
    mutationFn: () => usersApi.create({ ...form, organization: needsAgency ? form.organization || null : null }),
    onSuccess: (u) => {
      toast.show(form.password ? `${u.email} can now sign in.` : `Account created — a link to set the password was e-mailed to ${u.email}.`, "success");
      queryClient.invalidateQueries({ queryKey: ["users"] });
      queryClient.invalidateQueries({ queryKey: ["orgs"] });
      onClose();
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setErrors(err.fieldErrors());
        toast.show(err.message, "error");
      }
    },
  });

  const set = (key: keyof UserCreateInput) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }));

  return (
    <Modal
      open={open}
      title="New user"
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button loading={save.isPending} onClick={() => save.mutate()}>Create user</Button>
        </>
      }
    >
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <Select label="Role" value={form.role} error={errors.role} onChange={set("role")}>
          {(Object.keys(ROLE_LABELS) as Role[]).map((r) => (
            <option key={r} value={r}>{ROLE_LABELS[r]}</option>
          ))}
        </Select>
        {needsAgency && (
          <div className="animate-fade-up">
            <Select label="Agency" value={form.organization ?? ""} error={errors.organization} onChange={set("organization")}>
              <option value="">{agencies.isLoading ? "Loading agencies…" : "Choose an agency"}</option>
              {agencies.data?.items.map((o) => (
                <option key={o.id} value={o.id}>{o.name} · {o.city}</option>
              ))}
            </Select>
          </div>
        )}
        <Input label="Full name" value={form.full_name} error={errors.full_name} onChange={set("full_name")} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Input label="E-mail" type="email" autoComplete="off" value={form.email} error={errors.email} onChange={set("email")} />
          <Input label="Phone (optional)" type="tel" value={form.phone} error={errors.phone} onChange={set("phone")} />
        </div>
        <Input label="Password (optional)" type="password" autoComplete="new-password" value={form.password} error={errors.password}
          onChange={set("password")} hint="Set it now and share it, or leave blank to e-mail them a link to set their own." />
        {form.role === "SUPER_ADMIN" && (
          <p className="animate-fade-up rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800 ring-1 ring-amber-200">
            Super Admins have full access to every agency, user and setting on the platform.
          </p>
        )}
        <button type="submit" hidden />
      </form>
    </Modal>
  );
}
