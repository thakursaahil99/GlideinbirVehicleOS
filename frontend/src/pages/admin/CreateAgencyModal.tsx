import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { ApiError } from "@/api/client";
import { organizationsApi, type AgencyCreateInput } from "@/api/resources";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/FormField";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/toast-context";

const EMPTY: AgencyCreateInput = {
  name: "", email: "", phone: "", city: "", state: "", address: "", pincode: "", gst_number: "",
  admin_full_name: "", admin_email: "", admin_phone: "", admin_password: "",
};

/** Super Admin onboards an agency directly — it goes live (ACTIVE) with its first Agency Admin. */
export function CreateAgencyModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<AgencyCreateInput>(EMPTY);
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (open) {
      setForm(EMPTY);
      setErrors({});
    }
  }, [open]);

  const save = useMutation({
    mutationFn: () => organizationsApi.create(form),
    onSuccess: (org) => {
      toast.show(form.admin_password ? `${org.name} is live. ${form.admin_email} can sign in now.` : `${org.name} is live. Invite e-mailed to ${form.admin_email}.`, "success");
      queryClient.invalidateQueries({ queryKey: ["orgs"] });
      queryClient.invalidateQueries({ queryKey: ["users"] });
      onClose();
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setErrors(err.fieldErrors());
        toast.show(err.message, "error");
      }
    },
  });

  const set = (key: keyof AgencyCreateInput) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }));

  return (
    <Modal
      open={open}
      title="New agency"
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button loading={save.isPending} onClick={() => save.mutate()}>Create agency</Button>
        </>
      }
    >
      <form className="space-y-5" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <fieldset className="space-y-4">
          <legend className="mb-1 text-xs font-semibold uppercase tracking-wider text-brand-700">Agency</legend>
          <Input label="Agency name" value={form.name} error={errors.name} onChange={set("name")} />
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Business e-mail" type="email" value={form.email} error={errors.email} onChange={set("email")} />
            <Input label="Phone" type="tel" value={form.phone} error={errors.phone} onChange={set("phone")} />
            <Input label="City" value={form.city} error={errors.city} onChange={set("city")} />
            <Input label="State (optional)" value={form.state} error={errors.state} onChange={set("state")} />
            <Input label="Pincode (optional)" inputMode="numeric" value={form.pincode} error={errors.pincode} onChange={set("pincode")} />
            <Input label="GSTIN (optional)" value={form.gst_number} error={errors.gst_number} onChange={set("gst_number")} />
          </div>
          <Input label="Address (optional)" value={form.address} error={errors.address} onChange={set("address")} />
        </fieldset>
        <fieldset className="space-y-4 border-t border-slate-100 pt-4">
          <legend className="mb-1 pt-4 text-xs font-semibold uppercase tracking-wider text-brand-700">Agency Admin login</legend>
          <Input label="Admin full name" value={form.admin_full_name} error={errors.admin_full_name} onChange={set("admin_full_name")} />
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Admin e-mail" type="email" autoComplete="off" value={form.admin_email} error={errors.admin_email} onChange={set("admin_email")} />
            <Input label="Admin phone (optional)" type="tel" value={form.admin_phone} error={errors.admin_phone} onChange={set("admin_phone")} />
          </div>
          <Input label="Admin password (optional)" type="password" autoComplete="new-password" value={form.admin_password} error={errors.admin_password}
            onChange={set("admin_password")} hint="Leave blank to e-mail the admin a link to set their own password." />
        </fieldset>
        <button type="submit" hidden />
      </form>
    </Modal>
  );
}
