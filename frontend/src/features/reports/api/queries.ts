"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import type { ReportCollection } from "@/shared/api/types";
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
