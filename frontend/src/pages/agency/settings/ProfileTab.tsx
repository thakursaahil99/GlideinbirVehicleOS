import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useForm } from "react-hook-form";

import { organizationsApi } from "@/api/resources";
import { Button } from "@/components/ui/Button";
import { Alert, Card, Spinner } from "@/components/ui/Card";
import { Input, Textarea } from "@/components/ui/FormField";
import { useToast } from "@/components/ui/toast-context";
import { applyApiErrors } from "@/forms/applyApiErrors";
import { organizationProfileSchema, type OrganizationProfileValues } from "@/forms/schemas";
import { useAuth } from "@/hooks/useAuth";
import type { Organization } from "@/types/api";

import { useMyOrganization } from "../useMyOrganization";

const FIELDS = [
  "name", "legal_name", "email", "phone", "website", "description", "address", "city", "state", "pincode",
  "gst_number", "registration_number",
] as const;

const toFormValues = (org: Organization): OrganizationProfileValues =>
  Object.fromEntries(FIELDS.map((f) => [f, org[f] ?? ""])) as OrganizationProfileValues;

export function ProfileTab() {
  const { user, refreshUser } = useAuth();
  const { data: org, isLoading } = useMyOrganization();
  const canEdit = user?.role === "AGENCY_ADMIN";
  const toast = useToast();
  const queryClient = useQueryClient();

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isDirty },
  } = useForm({ resolver: zodResolver(organizationProfileSchema) });

  useEffect(() => {
    if (org) reset(toFormValues(org));
  }, [org, reset]);

  const mutation = useMutation({
    mutationFn: (values: OrganizationProfileValues) => organizationsApi.update(org!.id, values),
    onSuccess: async (updated) => {
      queryClient.setQueryData(["orgs", "mine", updated.id], updated);
      reset(toFormValues(updated));
      await refreshUser();
      toast.show("Agency profile saved.", "success");
    },
    onError: (err) => {
      const message = applyApiErrors(err, setError, FIELDS);
      if (message) toast.show(message, "error");
    },
  });

  if (isLoading) return <Spinner />;
  if (!org) return <Alert tone="danger">Agency not found.</Alert>;

  return (
    <>
      {!canEdit && (
        <div className="mb-4">
          <Alert>Only the agency admin can edit these details.</Alert>
        </div>
      )}
      <form onSubmit={handleSubmit((v) => mutation.mutate(v))} noValidate>
        <Card
          title="Profile"
          actions={
            canEdit && (
              <Button type="submit" size="sm" loading={mutation.isPending} disabled={!isDirty}>
                Save changes
              </Button>
            )
          }
        >
          <fieldset disabled={!canEdit} className="grid gap-4 sm:grid-cols-2">
            <Input label="Agency name" error={errors.name?.message} {...register("name")} />
            <Input label="Legal name" error={errors.legal_name?.message} {...register("legal_name")} />
            <Input label="E-mail" type="email" error={errors.email?.message} {...register("email")} />
            <Input label="Phone" type="tel" error={errors.phone?.message} {...register("phone")} />
            <Input label="Website" placeholder="https://" error={errors.website?.message} {...register("website")} />
            <Input label="GSTIN" error={errors.gst_number?.message} {...register("gst_number")} />
            <Input label="Registration no." error={errors.registration_number?.message} {...register("registration_number")} />
            <Input label="City" error={errors.city?.message} {...register("city")} />
            <Input label="State" error={errors.state?.message} {...register("state")} />
            <Input label="PIN code" error={errors.pincode?.message} {...register("pincode")} />
            <Textarea label="Address" wrapperClassName="sm:col-span-2" error={errors.address?.message} {...register("address")} />
            <Textarea label="Description" wrapperClassName="sm:col-span-2" error={errors.description?.message} {...register("description")} />
          </fieldset>
        </Card>
      </form>
    </>
  );
}
