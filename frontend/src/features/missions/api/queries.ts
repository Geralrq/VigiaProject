"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import type { Mission, MissionAnswer, MissionAnswerResult } from "@/shared/api/types";

export function useMissions() {
  return useQuery({
    queryKey: ["missions"],
    queryFn: ({ signal }) => api.get<Mission[]>("/missions/mine", undefined, signal),
  });
}

/** Responde una misión (una sola vez). La foto es opcional y ya viene comprimida. */
export function useRespondToMission() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      missionId,
      answer,
      photo,
    }: {
      missionId: string;
      answer: MissionAnswer;
      photo: File | null;
    }) => {
      const form = new FormData();
      form.set("answer", answer);
      if (photo) form.set("photo", photo, photo.name);
      return api.postForm<MissionAnswerResult>(`/missions/${missionId}/respuesta`, form);
    },
    onSuccess: () => {
      for (const key of ["missions", "leaderboard", "me"]) {
        void queryClient.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}
