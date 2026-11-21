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

// Espacio duro antes de «%»: que el número y el símbolo no se separen al cortar la línea.
export const percent = (value: number): string => `${Math.round(value * 100)} %`;

const numberFormat = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 1 });
export const formatNumber = (value: number): string => numberFormat.format(value);

const decimalFormat = new Intl.NumberFormat("es-CO", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
export const formatDecimal = (value: number): string => decimalFormat.format(value);

// Las fechas puras (AAAA-MM-DD) se interpretan en UTC: formatearlas en hora local correría el día.
const dayFormat = new Intl.DateTimeFormat("es-CO", { dateStyle: "medium", timeZone: "UTC" });
// Los instantes (con hora) se muestran en hora de Colombia, igual en servidor y navegador.
const instantFormat = new Intl.DateTimeFormat("es-CO", {
  dateStyle: "medium",
  timeZone: "America/Bogota",
});
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;

export const formatDate = (iso: string): string =>
  (DATE_ONLY.test(iso) ? dayFormat : instantFormat).format(new Date(iso));
