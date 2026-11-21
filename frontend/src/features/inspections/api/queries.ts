"use client";

import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import type {
  Inspection,
  InspectionFormIn,
  InspectionState,
  UserSummary,
} from "@/shared/api/types";

export const INSPECTION_STATES: readonly InspectionState[] = [
  "ABIERTO",
  "ASIGNADO",
  "EN_PROGRESO",
  "CERRADO",
];

export function useInspections() {
  return useQuery({
    queryKey: ["inspections"],
    queryFn: ({ signal }) => api.get<Inspection[]>("/inspections", { limit: 200 }, signal),
  });
}

export function useInspection(id: string) {
  return useQuery({
    queryKey: ["inspection", id],
    queryFn: ({ signal }) => api.get<Inspection>(`/inspections/${id}`, undefined, signal),
  });
}

/** Técnicos para asignar (solo AUTORIDAD y ADMIN; el backend devuelve id y nombre). */
export function useTechnicians(enabled: boolean) {
  return useQuery({
    queryKey: ["users", "TECNICO"],
    queryFn: ({ signal }) => api.get<UserSummary[]>("/users", { rol: "TECNICO" }, signal),
    enabled,
    staleTime: 5 * 60_000,
  });
}

function store(queryClient: QueryClient, inspection: Inspection): void {
  queryClient.setQueryData(["inspection", inspection.id], inspection);
  void queryClient.invalidateQueries({ queryKey: ["inspections"] });
}

export function useAssignInspection(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (tecnicoId: string) =>
      api.post<Inspection>(`/inspections/${id}/asignar`, { tecnico_id: tecnicoId }),
    onSuccess: (inspection) => store(queryClient, inspection),
  });
}

/** Sube una foto de evidencia (ya comprimida) y devuelve el ticket actualizado. */
export function useUploadInspectionPhoto(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (photo: File) => {
      const form = new FormData();
      form.set("foto", photo, photo.name);
      return api.postForm<{ path: string; inspection: Inspection }>(
        `/inspections/${id}/fotos`,
        form,
      );
    },
    onSuccess: ({ inspection }) => store(queryClient, inspection),
  });
}

export function useSaveInspectionForm(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (form: InspectionFormIn) =>
      api.put<Inspection>(`/inspections/${id}/formulario`, form),
    onSuccess: (inspection) => store(queryClient, inspection),
  });
}

export function useCloseInspection(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<Inspection>(`/inspections/${id}/cerrar`),
    onSuccess: (inspection) => store(queryClient, inspection),
  });
}

/** Descarga el informe PDF (el backend lo genera si aún no existe). */
export function useInspectionPdf(id: string) {
  return useMutation({ mutationFn: () => api.getBlob(`/inspections/${id}/pdf`) });
}
