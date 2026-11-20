"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import type { Profile } from "@/shared/api/types";
import { useSession } from "../hooks/useSession";

/** Perfil del usuario autenticado (GET /api/me). El rol sale siempre del backend. */
export function useMe() {
  const { status, session } = useSession();
  return useQuery({
    queryKey: ["me", session?.user.id ?? null],
    queryFn: ({ signal }) => api.get<Profile>("/me", undefined, signal),
    enabled: status === "authed",
    staleTime: 5 * 60_000,
  });
}
