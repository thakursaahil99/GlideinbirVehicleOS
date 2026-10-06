import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { vehiclesApi } from "@/api/customers";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Input, Select, Textarea } from "@/components/ui/FormField";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/toast-context";
import type { Vehicle } from "@/types/api";
import { FUEL_LABELS, VEHICLE_TYPE_LABELS } from "@/utils/format";

type FormState = Record<string, string>;

const FIELDS = [
  "vehicle_type", "brand", "model", "variant", "registration_number", "vin", "fuel_type", "manufacturing_year",
  "color", "odometer", "insurance_expiry", "pollution_expiry", "registration_expiry", "chassis_number",
  "engine_number", "notes",
] as const;

const EMPTY: FormState = Object.fromEntries(FIELDS.map((f) => [f, ""]));

function toForm(v: Vehicle | null): FormState {
  if (!v) return { ...EMPTY, vehicle_type: "CAR", fuel_type: "PETROL" };
  return Object.fromEntries(FIELDS.map((f) => [f, v[f] === null || v[f] === undefined ? "" : String(v[f])]));
}

function toPayload(form: FormState): Partial<Vehicle> {
  const out: Record<string, unknown> = {};
  for (const f of FIELDS) {
    const value = form[f].trim();
    if (["manufacturing_year", "odometer"].includes(f)) out[f] = value ? Number(value) : null;
    else if (f.endsWith("_expiry")) out[f] = value || null;
    else out[f] = value;
  }
  return out as Partial<Vehicle>;
}

interface Props {
  open: boolean;
  onClose: () => void;
  vehicle: Vehicle | null;
  /** Required for agency users adding a vehicle to a customer. */
  customerId?: string;
}

export function VehicleFormModal({ open, onClose, vehicle, customerId }: Props) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<FormState>(toForm(null));
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (open) {
      setForm(toForm(vehicle));
      setErrors({});
    }
  }, [open, vehicle]);

  const save = useMutation({
    mutationFn: () => {
      const payload = toPayload(form);
      if (vehicle) return vehiclesApi.update(vehicle.id, payload);
      return vehiclesApi.create(customerId ? { ...payload, customer: customerId } : payload);
    },
    onSuccess: () => {
      toast.show(vehicle ? "Vehicle updated." : "Vehicle added.", "success");
      queryClient.invalidateQueries({ queryKey: ["vehicles"] });
      queryClient.invalidateQueries({ queryKey: ["customers"] });
      onClose();
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setErrors(err.fieldErrors());
        toast.show(err.message, "error");
      }
    },
  });

  const field = (name: (typeof FIELDS)[number]) => ({
    value: form[name],
    error: errors[name],
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setForm({ ...form, [name]: e.target.value }),
  });

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={vehicle ? `Edit ${vehicle.brand} ${vehicle.model}` : "Add vehicle"}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button loading={save.isPending} onClick={() => save.mutate()}>{vehicle ? "Save" : "Add vehicle"}</Button>
        </>
      }
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Select label="Type" {...field("vehicle_type")}>
          {Object.entries(VEHICLE_TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
        <Select label="Fuel" {...field("fuel_type")}>
          {Object.entries(FUEL_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
        <Input label="Brand" placeholder="Maruti Suzuki" {...field("brand")} />
        <Input label="Model" placeholder="Swift" {...field("model")} />
        <Input label="Variant" {...field("variant")} />
        <Input label="Registration no." placeholder="MH 12 AB 1234" {...field("registration_number")} />
        <Input label="Year" type="number" inputMode="numeric" {...field("manufacturing_year")} />
        <Input label="Odometer (km)" type="number" inputMode="numeric" {...field("odometer")} />
        <Input label="Colour" {...field("color")} />
        <Input label="VIN" maxLength={17} {...field("vin")} />
        <Input label="Insurance expiry" type="date" {...field("insurance_expiry")} />
        <Input label="PUC expiry" type="date" {...field("pollution_expiry")} />
        <Input label="Registration expiry" type="date" {...field("registration_expiry")} />
        <Input label="Chassis no." {...field("chassis_number")} />
        <Input label="Engine no." {...field("engine_number")} wrapperClassName="sm:col-span-2" />
        <Textarea label="Notes" {...field("notes")} wrapperClassName="sm:col-span-2" />
      </div>
    </Modal>
  );
}
