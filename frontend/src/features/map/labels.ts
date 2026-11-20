import type { AnomalyState, AnomalyType, RiskLevel } from "@/shared/api/types";

export const ANOMALY_TYPE_LABELS: Record<AnomalyType, string> = {
  DEFORESTACION: "Deforestación",
  INCENDIO: "Incendio",
};

export const ANOMALY_STATE_LABELS: Record<AnomalyState, string> = {
  DETECTADA: "Detectada",
  EN_VERIFICACION: "En verificación",
  CONFIRMADA: "Confirmada",
  FALSO_POSITIVO: "Falso positivo",
};

export const RISK_LABELS: Record<RiskLevel, string> = {
  BAJO: "Bajo",
  MEDIO: "Medio",
  ALTO: "Alto",
  CRITICO: "Crítico",
};

export const percent = (value: number): string => `${Math.round(value * 100)} %`;

const numberFormat = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 1 });
export const formatNumber = (value: number): string => numberFormat.format(value);

const dateFormat = new Intl.DateTimeFormat("es-CO", { dateStyle: "medium" });
export const formatDate = (iso: string): string => dateFormat.format(new Date(iso));
