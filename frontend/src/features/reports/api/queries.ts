"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import type {
  ReportCategory,
  ReportCollection,
  ReportFeature,
  Urgency,
} from "@/shared/api/types";
import { bboxParam, type Bbox } from "@/shared/geo";

/** Reportes ciudadanos: CIUDADANO ve los suyos; AUTORIDAD y ADMIN todos (lo decide el backend). */
export function useReports(bbox: Bbox | null, enabled: boolean) {
  const bboxValue = bboxParam(bbox);
  return useQuery({
    queryKey: ["reports", bboxValue],
    queryFn: ({ signal }) =>
      api.get<ReportCollection>("/reports", { bbox: bboxValue, limit: 500 }, signal),
    enabled: enabled && bbox !== null,
    placeholderData: keepPreviousData,
  });
}

export interface NewReport {
  category: ReportCategory;
  urgency: Urgency;
  lat: number;
  lng: number;
  description: string;
  /** Foto ya comprimida en el cliente (máx. 1600 px, JPEG). */
  photo: File | null;
}

/** Crea un reporte (multipart). El cuerpo completo debe quedar bajo el límite de 4,5 MB de Vercel. */
export function useCreateReport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (report: NewReport) => {
      const form = new FormData();
      form.set("category", report.category);
      form.set("urgency", report.urgency);
      form.set("lat", String(report.lat));
      form.set("lng", String(report.lng));
      if (report.description.trim()) form.set("description", report.description.trim());
      if (report.photo) form.set("photo", report.photo, report.photo.name);
      return api.postForm<ReportFeature>("/reports", form);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["reports"] }),
  });
}
