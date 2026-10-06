import { useSearchParams } from "react-router";

import { PageHeader } from "@/components/ui/Card";
import { Tabs } from "@/components/ui/Tabs";
import { useAuth } from "@/hooks/useAuth";

import { BookingRulesTab } from "./settings/BookingRulesTab";
import { ClosuresTab } from "./settings/ClosuresTab";
import { HoursTab } from "./settings/HoursTab";
import { ProfileTab } from "./settings/ProfileTab";
import { ResourcesTab } from "./settings/ResourcesTab";

const TABS = [
  { key: "profile", label: "Profile" },
  { key: "hours", label: "Working hours" },
  { key: "closures", label: "Closures & special days" },
  { key: "resources", label: "Resources" },
  { key: "rules", label: "Booking rules" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

export function AgencySettingsPage() {
  const { user } = useAuth();
  const canEdit = user?.role === "AGENCY_ADMIN";
  const [params, setParams] = useSearchParams();
  const tab = (TABS.find((t) => t.key === params.get("tab"))?.key ?? "profile") as TabKey;

  return (
    <>
      <PageHeader title="Agency settings" description="Profile, opening hours, closures, resources and booking rules." />
      <Tabs items={[...TABS]} active={tab} onChange={(k) => setParams({ tab: k }, { replace: true })} />
      {tab === "profile" && <ProfileTab />}
      {tab === "hours" && <HoursTab canEdit={canEdit} />}
      {tab === "closures" && <ClosuresTab canEdit={canEdit} />}
      {tab === "resources" && <ResourcesTab canEdit={canEdit} />}
      {tab === "rules" && <BookingRulesTab canEdit={canEdit} />}
    </>
  );
}
