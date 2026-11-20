"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import type {
  AnomalyCollection,
  AnomalyFeature,
  AnomalyImages,
  HotspotCollection,
  ScanSummary,
  Zone,
  ZoneReadings,
} from "@/shared/api/types";
import { bboxParam, daysAgoISO, type Bbox } from "@/shared/geo";

const HOTSPOT_WINDOW_DAYS = 30;
const MAX_IMAGE_POLLS = 4;
const IMAGE_POLL_MS = 5_000;

export function useZones() {
  return useQuery({
    queryKey: ["zones"],
    queryFn: ({ signal }) => api.get<Zone[]>("/zones", undefined, signal),
    staleTime: 5 * 60_000,
  });
}

export function useAnomalies(bbox: Bbox | null) {
  const bboxValue = bboxParam(bbox);
  return useQuery({
    queryKey: ["anomalies", bboxValue],
    queryFn: ({ signal }) =>
      api.get<AnomalyCollection>("/anomalies", { bbox: bboxValue, limit: 500 }, signal),
    enabled: bbox !== null,
    placeholderData: keepPreviousData,
  });
}

export function useHotspots(bbox: Bbox | null, enabled: boolean) {
  const bboxValue = bboxParam(bbox);
  const start = daysAgoISO(HOTSPOT_WINDOW_DAYS);
  return useQuery({
    queryKey: ["hotspots", bboxValue, start],
    queryFn: ({ signal }) =>
      api.get<HotspotCollection>("/hotspots", { bbox: bboxValue, start, limit: 2000 }, signal),
    enabled: enabled && bbox !== null,
    placeholderData: keepPreviousData,
  });
}

/** Imágenes antes/después. Si el backend aún no las tiene (URL null) reintenta unas veces. */
export function useAnomalyImages(anomalyId: string | null) {
  return useQuery({
    queryKey: ["anomaly-images", anomalyId],
    queryFn: ({ signal }) =>
      api.get<AnomalyImages>(`/anomalies/${anomalyId}/images`, undefined, signal),
    enabled: anomalyId !== null,
    staleTime: 30 * 60_000, // las URL firmadas duran 1 h
    refetchInterval: (query) => {
      const data = query.state.data;
      const missing = data && (data.before_url === null || data.after_url === null);
      return missing && query.state.dataUpdateCount < MAX_IMAGE_POLLS ? IMAGE_POLL_MS : false;
    },
  });
}

export function useZoneReadings(zoneId: string | null, index = "NDVI", days = 90) {
  return useQuery({
    queryKey: ["zone-readings", zoneId, index, days],
    queryFn: ({ signal }) =>
      api.get<ZoneReadings>(`/zones/${zoneId}/readings`, { index, days }, signal),
    enabled: zoneId !== null,
  });
}

/** ADMIN: escanea ahora todas las zonas activas. */
export function useScanNow() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<ScanSummary>("/admin/scan"),
    onSuccess: () => {
      for (const key of ["anomalies", "hotspots", "zone-readings", "alerts"]) {
        void queryClient.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}

/** ADMIN: confirma una anomalía (publica el evento que genera la alerta). */
export function useConfirmAnomaly() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (anomalyId: string) =>
      api.post<AnomalyFeature>(`/admin/anomalies/${anomalyId}/confirm`),
    onSuccess: () => {
      for (const key of ["anomalies", "alerts"]) {
        void queryClient.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}
