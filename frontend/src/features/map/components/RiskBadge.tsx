import type { RiskLevel } from "@/shared/api/types";
import { RiskGlyph } from "@/shared/ui/icons/Icon";
import { RISK_LABELS } from "../labels";

const LEVEL_BARS: Record<RiskLevel, 1 | 2 | 3 | 4> = { BAJO: 1, MEDIO: 2, ALTO: 3, CRITICO: 4 };

/** Nivel de riesgo: glifo de 1–4 barras + etiqueta; nunca solo color (ALTO y CRÍTICO se parecen). */
export function RiskBadge({ level }: { level: RiskLevel }) {
  return (
    <span className="risk-badge" data-level={level}>
      <RiskGlyph bars={LEVEL_BARS[level]} />
      {RISK_LABELS[level]}
    </span>
  );
}
