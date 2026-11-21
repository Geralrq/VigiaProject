import type { InspectionState, RiskLevel } from "@/shared/api/types";

export const STATE_LABELS: Record<InspectionState, string> = {
  ABIERTO: "Abierto",
  ASIGNADO: "Asignado",
  EN_PROGRESO: "En progreso",
  CERRADO: "Cerrado",
};

const RISK_LEVELS: readonly string[] = ["BAJO", "MEDIO", "ALTO", "CRITICO"];

/** El backend entrega el nivel como texto: solo se pinta el badge si es un nivel conocido. */
export function asRiskLevel(value: string): RiskLevel | null {
  return RISK_LEVELS.includes(value) ? (value as RiskLevel) : null;
}

export const FORM_FIELD_LABELS: Record<string, string> = {
  hallazgos: "Hallazgos",
  causa_probable: "Causa probable",
  area_verificada_ha: "Área verificada (ha)",
  fotos: "Al menos una foto en el informe",
};

/**
 * El backend responde 422 con «El formulario está incompleto; falta: a, b.».
 * Devuelve los campos citados (vacío si el mensaje no tiene ese formato).
 */
export function parseMissingFields(message: string): string[] {
  const match = /falta:\s*(.+?)\.?$/i.exec(message);
  return match ? match[1].split(",").map((field) => field.trim()).filter(Boolean) : [];
}
