"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import type { Profile, ProfileUpdate, TelegramLink } from "@/shared/api/types";

/** Edita el nombre y/o la ubicación propios (PATCH /api/me). El rol no se puede cambiar. */
export function useUpdateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (changes: ProfileUpdate) => api.patch<Profile>("/me", changes),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["me"] }),
  });
}

/** Pide un código de vinculación de Telegram (cada llamada emite uno nuevo, válido 10 minutos). */
export function useTelegramLink() {
  return useMutation({
    mutationFn: () => api.get<TelegramLink>("/me/telegram-link"),
  });
}

/** Solo con APP_MODE distinto de live: fija el chat_id a mano (el backend lo rechaza en live). */
export function useSetTelegramChat() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (chatId: number) =>
      api.patch<{ chat_id: number }>("/me/telegram", { chat_id: chatId }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["me"] }),
  });
}
