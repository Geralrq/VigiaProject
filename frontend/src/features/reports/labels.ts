import type { ReportCategory, Urgency } from "@/shared/api/types";

export const CATEGORY_LABELS: Record<ReportCategory, string> = {
  DEFORESTACION: "Deforestación",
  INCENDIO: "Incendio",
  MINERIA_ILEGAL: "Minería ilegal",
  CAZA_FURTIVA: "Caza furtiva",
  CONTAMINACION: "Contaminación",
  OTRO: "Otro",
};

export const CATEGORY_ORDER: readonly ReportCategory[] = [
  "INCENDIO",
  "DEFORESTACION",
  "MINERIA_ILEGAL",
  "CAZA_FURTIVA",
  "CONTAMINACION",
  "OTRO",
];

export const URGENCY_OPTIONS: readonly { value: Urgency; label: string; hint: string }[] = [
  { value: "BAJA", label: "Baja", hint: "puede esperar" },
  { value: "MEDIA", label: "Media", hint: "revisar pronto" },
  { value: "ALTA", label: "Alta", hint: "está ocurriendo ahora" },
];
