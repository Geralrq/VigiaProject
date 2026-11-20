"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import type { AlertCollection } from "@/shared/api/types";

export function useAlerts(enabled: boolean) {
  return useQuery({
    queryKey: ["alerts"],
    queryFn: ({ signal }) => api.get<AlertCollection>("/alerts", { limit: 200 }, signal),
    enabled,
  });
}
