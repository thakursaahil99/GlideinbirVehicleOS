import { useQuery } from "@tanstack/react-query";

import { organizationsApi } from "@/api/resources";
import { useAuth } from "@/hooks/useAuth";

/** The current agency user's organization. The backend resolves the tenant from the session, not from this id. */
export function useMyOrganization() {
  const { user } = useAuth();
  const orgId = user?.organization?.id;
  return useQuery({
    queryKey: ["orgs", "mine", orgId],
    queryFn: () => organizationsApi.get(orgId!),
    enabled: Boolean(orgId),
  });
}
