"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import type { LeaderboardEntry } from "@/shared/api/types";

export function useLeaderboard() {
  return useQuery({
    queryKey: ["leaderboard"],
    queryFn: ({ signal }) => api.get<LeaderboardEntry[]>("/leaderboard", { limit: 50 }, signal),
  });
}
