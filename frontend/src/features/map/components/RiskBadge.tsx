import type { RiskLevel } from "@/shared/api/types";
import { RISK_LABELS } from "../labels";

const LEVEL_BARS: Record<RiskLevel, number> = { BAJO: 1, MEDIO: 2, ALTO: 3, CRITICO: 4 };

/** Nivel de riesgo: glifo de 1–4 barras + etiqueta; nunca solo color (ALTO y CRÍTICO se parecen). */
export function RiskBadge({ level }: { level: RiskLevel }) {
  return (
    <span className="risk-badge" data-level={level}>
      <span className="risk-bars" aria-hidden="true">
        {[1, 2, 3, 4].map((bar) => (
          <span key={bar} data-on={bar <= LEVEL_BARS[level]} />
        ))}
      </span>
      {RISK_LABELS[level]}
    </span>
  );
}
