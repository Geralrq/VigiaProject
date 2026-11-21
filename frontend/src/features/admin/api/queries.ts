"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import type { ManagedUser, Role, UserPage } from "@/shared/api/types";

export const USERS_PAGE_SIZE = 20;

export interface UsersFilter {
  search: string;
  role: Role | null;
  page: number;
}

/** Usuarios para el ADMIN (GET /api/admin/users). Ubicación y Telegram llegan solo como sí/no. */
export function useAdminUsers({ search, role, page }: UsersFilter) {
  return useQuery({
    queryKey: ["admin-users", { search, role, page }],
    queryFn: ({ signal }) =>
      api.get<UserPage>(
        "/admin/users",
        { q: search || undefined, rol: role, page, page_size: USERS_PAGE_SIZE },
        signal,
      ),
    placeholderData: keepPreviousData, // al paginar o filtrar, la tabla no parpadea
  });
}

/** Cambia el rol (PATCH /api/admin/users/{id}/rol). El backend impide el propio y el del último ADMIN. */
export function useChangeUserRole() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: Role }) =>
      api.patch<ManagedUser>(`/admin/users/${userId}/rol`, { rol: role }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
  });
}
