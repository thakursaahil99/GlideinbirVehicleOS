import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, CheckCircle2, Clock, CreditCard, MapPin, Smartphone, Truck } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";

import { ApiError } from "@/api/client";
import { vehiclesApi } from "@/api/customers";
import { availabilityApi, bookingsApi, paymentsApi } from "@/api/operations";
import { catalogApi, directoryApi } from "@/api/services";
import { Button } from "@/components/ui/Button";
import { Alert, Card, EmptyState, PageHeader, Skeleton } from "@/components/ui/Card";
import { Textarea } from "@/components/ui/FormField";
import { Toggle } from "@/components/ui/Tabs";
import { useToast } from "@/components/ui/toast-context";
import type { CatalogService, Vehicle, VendorOffer } from "@/types/api";
import type { Booking, Payment, Slot } from "@/types/operations";
import { CATEGORY_LABELS, cn, dayLabel, formatDuration, inr, timeOnly } from "@/utils/format";

import { vehicleIcon } from "./CustomerVehiclesPage";

const STEPS = ["Vehicle", "Service", "Workshop", "Date", "Time", "Review", "Payment", "Done"] as const;

function Stepper({ step }: { step: number }) {
  return (
    <ol className="mb-6 flex items-center gap-1.5 overflow-x-auto pb-1" aria-label="Booking progress">
      {STEPS.map((label, i) => (
        <li key={label} className="flex items-center gap-1.5">
          <span
            className={cn(
              "flex h-7 shrink-0 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium transition-all duration-300",
              i < step && "bg-brand-100 text-brand-700",
              i === step && "bg-gradient-to-r from-brand-500 to-brand-700 text-white shadow-[var(--shadow-glow)]",
              i > step && "bg-slate-100 text-slate-400",
            )}
          >
            {i < step ? <Check className="h-3.5 w-3.5" /> : <span>{i + 1}</span>}
            <span className={cn(i === step ? "inline" : "hidden sm:inline")}>{label}</span>
          </span>
          {i < STEPS.length - 1 && <span className="h-px w-3 shrink-0 bg-slate-200" />}
        </li>
      ))}
    </ol>
  );
}

function ChoiceCard({ selected, onClick, children }: { selected: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={cn(
        "w-full rounded-2xl bg-white p-4 text-left shadow-[var(--shadow-soft)] ring-1 transition-all duration-200 active:scale-[0.99]",
        selected ? "ring-2 ring-brand-500 shadow-[var(--shadow-glow)]" : "ring-slate-200/70 hover:-translate-y-0.5 hover:shadow-[var(--shadow-lift)]",
      )}
    >
      {children}
    </button>
  );
}

export function BookServicePage() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [vehicle, setVehicle] = useState<Vehicle | null>(null);
  const [service, setService] = useState<CatalogService | null>(null);
  const [offer, setOffer] = useState<VendorOffer | null>(null);
  const [day, setDay] = useState<string | null>(null);
  const [slot, setSlot] = useState<Slot | null>(null);
  const [notes, setNotes] = useState("");
  const [pickup, setPickup] = useState(false);
  const [pickupAddress, setPickupAddress] = useState("");
  const [booking, setBooking] = useState<Booking | null>(null);
  const [pendingPayment, setPendingPayment] = useState<Payment | null>(null);
  const [sort, setSort] = useState<"price" | "-price">("price");

  const vehicles = useQuery({ queryKey: ["vehicles", "mine"], queryFn: () => vehiclesApi.list({ page_size: 100 }) });
  const services = useQuery({
    queryKey: ["catalog", "for", vehicle?.vehicle_type],
    queryFn: () => catalogApi.list({ vehicle_type: vehicle!.vehicle_type, page_size: 100 }),
    enabled: Boolean(vehicle),
  });
  const offers = useQuery({
    queryKey: ["compare", service?.slug, vehicle?.vehicle_type, sort],
    queryFn: () => directoryApi.compare({ service: service!.slug, vehicle_type: vehicle!.vehicle_type, ordering: sort }),
    enabled: Boolean(service && vehicle),
  });
  const days = useQuery({
    queryKey: ["availability", "days", offer?.offer_id],
    queryFn: () => availabilityApi.days(offer!.offer_id, 21),
    enabled: Boolean(offer),
  });
  const slots = useQuery({
    queryKey: ["availability", "slots", offer?.offer_id, day],
    queryFn: () => availabilityApi.slots(offer!.offer_id, day!),
    enabled: Boolean(offer && day),
    refetchInterval: 30_000, // availability is live — keep it fresh while the customer decides
  });

  const totalWithTax = useMemo(() => (offer ? Number(offer.offer_price) * 1.18 : 0), [offer]);

  const create = useMutation({
    mutationFn: () =>
      bookingsApi.create({
        vendor_service: offer!.offer_id, vehicle: vehicle!.id, start_datetime: slot!.start, customer_notes: notes,
        pickup_requested: pickup, pickup_address: pickup ? pickupAddress : "",
      }),
    onSuccess: async (b) => {
      setBooking(b);
      queryClient.invalidateQueries({ queryKey: ["bookings"] });
      const pending = await paymentsApi.list({ booking: b.id, status: "PENDING" });
      if (pending.items.length) {
        setPendingPayment(pending.items[0]);
        setStep(6);
      } else {
        setStep(7);
      }
    },
    onError: (err) => {
      const message = err instanceof ApiError ? err.message : "Booking failed.";
      toast.show(message, "error");
      // Slot just taken, or this vehicle is already booked then: go back and pick another time.
      if (err instanceof ApiError && ["BOOKING_SLOT_UNAVAILABLE", "VEHICLE_ALREADY_BOOKED"].includes(err.code)) {
        setSlot(null);
        slots.refetch();
        setStep(4);
      }
    },
  });

  const pay = useMutation({
    mutationFn: (method: string) =>
      paymentsApi.pay({ payment: pendingPayment!.id, method, idempotency_key: `${pendingPayment!.id}-${method}-${Date.now()}` }),
    onSuccess: (p) => {
      if (p.status === "SUCCEEDED") {
        toast.show("Payment successful.", "success");
        setStep(7);
      } else {
        toast.show(p.failure_reason || "Payment failed. Try another method.", "error");
      }
    },
    onError: (err) => toast.show(err instanceof ApiError ? err.message : "Payment failed.", "error"),
  });

  const back = () => setStep((s) => Math.max(0, s - 1));

  return (
    <>
      <PageHeader title="Book a service" description="Pick a vehicle, compare workshops and choose a live time slot." />
      <Stepper step={step} />

      {step > 0 && step < 6 && (
        <button type="button" onClick={back} className="mb-4 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800">
          <ArrowLeft className="h-4 w-4" /> Back
        </button>
      )}

      {step === 0 && (
        <section className="animate-fade-up">
          <h2 className="mb-3 text-lg font-semibold">Which vehicle?</h2>
          {vehicles.isLoading ? <Skeleton rows={3} /> : vehicles.data?.items.length === 0 ? (
            <Card><EmptyState title="Add a vehicle first" description="You need at least one vehicle to book a service." />
              <div className="flex justify-center"><Link to="/customer/vehicles"><Button>Add vehicle</Button></Link></div></Card>
          ) : (
            <div className="stagger grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {vehicles.data?.items.map((v) => {
                const Icon = vehicleIcon(v.vehicle_type);
                return (
                  <ChoiceCard key={v.id} selected={vehicle?.id === v.id} onClick={() => { setVehicle(v); setService(null); setOffer(null); setStep(1); }}>
                    <div className="flex items-center gap-3">
                      <span className="rounded-xl bg-gradient-to-br from-brand-500 to-accent-500 p-2.5 text-white"><Icon className="h-5 w-5" /></span>
                      <div className="min-w-0">
                        <p className="truncate font-semibold text-slate-900">{v.brand} {v.model}</p>
                        <p className="font-mono text-sm text-slate-500">{v.registration_number}</p>
                      </div>
                    </div>
                  </ChoiceCard>
                );
              })}
            </div>
          )}
        </section>
      )}

      {step === 1 && (
        <section className="animate-fade-up">
          <h2 className="mb-3 text-lg font-semibold">What does it need?</h2>
          {services.isLoading ? <Skeleton rows={4} /> : (
            <div className="stagger grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {services.data?.items.map((s) => (
                <ChoiceCard key={s.id} selected={service?.id === s.id} onClick={() => { setService(s); setOffer(null); setStep(2); }}>
                  <p className="font-semibold text-slate-900">{s.name}</p>
                  <p className="mt-0.5 text-xs text-slate-500">{CATEGORY_LABELS[s.category]} · ~{formatDuration(s.default_duration)}</p>
                  <p className="mt-2 text-sm text-slate-600">from <span className="font-semibold text-brand-700">{inr(s.base_price)}</span></p>
                </ChoiceCard>
              ))}
            </div>
          )}
        </section>
      )}

      {step === 2 && (
        <section className="animate-fade-up">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-lg font-semibold">Compare workshops</h2>
            <div className="inline-flex rounded-xl bg-slate-200/60 p-1 text-xs">
              {(["price", "-price"] as const).map((o) => (
                <button key={o} type="button" onClick={() => setSort(o)}
                  className={cn("rounded-lg px-3 py-1.5 font-medium", sort === o ? "bg-white text-brand-700 shadow" : "text-slate-500")}>
                  {o === "price" ? "Lowest price" : "Highest price"}
                </button>
              ))}
            </div>
          </div>
          {offers.isLoading ? <Skeleton rows={3} /> : offers.data?.items.length === 0 ? (
            <Card><EmptyState title="No workshop offers this yet" description="Try another service." /></Card>
          ) : (
            <div className="stagger space-y-3">
              {offers.data?.items.map((o) => (
                <ChoiceCard key={o.id} selected={offer?.id === o.id} onClick={() => { setOffer(o); setDay(null); setSlot(null); setStep(3); }}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-semibold text-slate-900">{o.name}</p>
                      <p className="mt-0.5 flex items-center gap-1 text-xs text-slate-500"><MapPin className="h-3.5 w-3.5" />{o.city}{o.state ? `, ${o.state}` : ""}</p>
                      <p className="mt-1 flex items-center gap-1 text-xs text-slate-500"><Clock className="h-3.5 w-3.5" />{formatDuration(o.offer_duration)}</p>
                    </div>
                    <div className="text-right">
                      <p className="font-display text-xl font-semibold text-brand-700">{inr(o.offer_price)}</p>
                      <p className="text-[11px] text-slate-400">+ GST</p>
                    </div>
                  </div>
                </ChoiceCard>
              ))}
            </div>
          )}
        </section>
      )}

      {step === 3 && (
        <section className="animate-fade-up">
          <h2 className="mb-3 text-lg font-semibold">Pick a day</h2>
          {days.isLoading ? <Skeleton rows={2} /> : (
            <div className="stagger grid grid-cols-3 gap-2 sm:grid-cols-5 lg:grid-cols-7">
              {days.data?.days.map((d) => {
                const open = d.bookable && d.available_slots > 0;
                return (
                  <button key={d.date} type="button" disabled={!open}
                    onClick={() => { setDay(d.date); setSlot(null); setStep(4); }}
                    className={cn("rounded-xl px-2 py-3 text-center ring-1 transition-all",
                      open ? "bg-white ring-slate-200 hover:ring-brand-400 active:scale-95" : "cursor-not-allowed bg-slate-50 text-slate-300 ring-slate-100",
                      day === d.date && "ring-2 ring-brand-500")}>
                    <span className="block text-xs font-medium">{dayLabel(d.date)}</span>
                    <span className={cn("mt-1 block text-[11px]", open ? "text-emerald-600" : "text-slate-300")}>
                      {d.total_slots === 0 ? "Closed" : open ? `${d.available_slots} free` : "Full"}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </section>
      )}

      {step === 4 && (
        <section className="animate-fade-up">
          <h2 className="mb-1 text-lg font-semibold">Pick a time · {day && dayLabel(day)}</h2>
          <p className="mb-3 text-xs text-slate-500">Times are live from the workshop's schedule and update automatically.</p>
          {slots.isLoading ? <Skeleton rows={2} /> : slots.data?.slots.length === 0 ? (
            <Card><EmptyState title="No times left on this day" /></Card>
          ) : (
            <div className="stagger grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-6">
              {slots.data?.slots.map((s) => (
                <button key={s.start} type="button" disabled={!s.available} onClick={() => { setSlot(s); setStep(5); }}
                  className={cn("rounded-xl py-3 text-sm font-medium ring-1 transition-all",
                    s.available ? "bg-white text-slate-800 ring-slate-200 hover:ring-brand-400 active:scale-95" : "cursor-not-allowed bg-slate-50 text-slate-300 line-through ring-slate-100",
                    slot?.start === s.start && "bg-brand-600 text-white ring-brand-600")}>
                  {timeOnly(s.start)}
                </button>
              ))}
            </div>
          )}
        </section>
      )}

      {step === 5 && vehicle && service && offer && slot && (
        <section className="animate-fade-up space-y-4">
          <Card title="Review your booking">
            <dl className="grid gap-3 text-sm sm:grid-cols-2">
              {[["Vehicle", `${vehicle.brand} ${vehicle.model} · ${vehicle.registration_number}`], ["Service", service.name],
                ["Workshop", `${offer.name}, ${offer.city}`], ["When", `${dayLabel(day!)} · ${timeOnly(slot.start)} – ${timeOnly(slot.end)}`],
                ["Price", `${inr(offer.offer_price)} + GST ≈ ${inr(totalWithTax.toFixed(2))}`]].map(([k, v]) => (
                <div key={k}><dt className="text-xs text-slate-500">{k}</dt><dd className="font-medium text-slate-900">{v}</dd></div>
              ))}
            </dl>
          </Card>
          <Card>
            <div className="space-y-4">
              <Textarea label="Anything the workshop should know? (optional)" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. squeaking brakes, AC not cooling" />
              <Toggle label="Request pickup" description="If the workshop offers pickup for this service." checked={pickup} onChange={setPickup} />
              {pickup && <Textarea label="Pickup address" value={pickupAddress} onChange={(e) => setPickupAddress(e.target.value)} />}
            </div>
          </Card>
          <Button className="w-full sm:w-auto" loading={create.isPending} onClick={() => create.mutate()}>
            <Truck className="h-4 w-4" /> Confirm booking
          </Button>
        </section>
      )}

      {step === 6 && pendingPayment && (
        <section className="animate-fade-up space-y-4">
          <Alert tone="info">This workshop asks for payment when booking. Amount due: <b>{inr(pendingPayment.amount)}</b></Alert>
          <div className="grid gap-3 sm:grid-cols-3">
            {[["UPI", "UPI", Smartphone], ["CARD", "Card", CreditCard], ["MOCK", "Test gateway", CreditCard]].map(([method, label, Icon]) => (
              <ChoiceCard key={method as string} selected={false} onClick={() => pay.mutate(method as string)}>
                <span className="flex items-center gap-3 font-medium text-slate-900">
                  <Icon className="h-5 w-5 text-brand-600" /> Pay with {label as string}
                </span>
              </ChoiceCard>
            ))}
          </div>
          <p className="text-xs text-slate-500">Development mode: payments go through the mock gateway — no real money moves.</p>
          {pay.isPending && <Skeleton rows={1} />}
          <Button variant="ghost" onClick={() => setStep(7)}>Pay later</Button>
        </section>
      )}

      {step === 7 && booking && (
        <section className="animate-scale-in">
          <Card>
            <div className="flex flex-col items-center py-6 text-center">
              <span className="relative mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-gradient-to-br from-emerald-400 to-emerald-600 text-white shadow-lg">
                <CheckCircle2 className="h-8 w-8" />
              </span>
              <h2 className="text-xl font-semibold text-slate-900">Booking {booking.status === "CONFIRMED" ? "confirmed" : "received"}!</h2>
              <p className="mt-1 text-sm text-slate-500">{booking.booking_number} · {dayLabel(booking.booking_date)} at {timeOnly(booking.start_datetime)}</p>
              <p className="mt-1 text-sm text-slate-500">{booking.organization.name} will {booking.status === "CONFIRMED" ? "see you then" : "confirm shortly"}.</p>
              <div className="mt-6 flex flex-col gap-2 sm:flex-row">
                <Button onClick={() => navigate(`/customer/bookings/${booking.id}`)}>View booking</Button>
                <Button variant="secondary" onClick={() => { setStep(0); setVehicle(null); setService(null); setOffer(null); setSlot(null); setBooking(null); }}>Book another</Button>
              </div>
            </div>
          </Card>
        </section>
      )}
    </>
  );
}
