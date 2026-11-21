import type { RiskLevel } from "@/shared/api/types";
import { Icon } from "@/shared/ui/icons/Icon";
import { RiskBadge } from "./RiskBadge";

const LEVELS: readonly RiskLevel[] = ["BAJO", "MEDIO", "ALTO", "CRITICO"];

/**
 * Leyenda: qué significa cada marcador y color. Plegable con <details> (teclado y lector de
 * pantalla nativos). La escala y la atribución son controles de MapLibre, siempre visibles.
 */
export function MapLegend({ open = true }: { open?: boolean }) {
  return (
    <details className="map-legend" open={open}>
      <summary>Leyenda</summary>
      <div className="legend-body">
        <p className="legend-title">Alertas por nivel de riesgo</p>
        <ul>
          {LEVELS.map((level) => (
            <li key={level}>
              <RiskBadge level={level} />
            </li>
          ))}
        </ul>
        <p className="legend-title">Marcadores</p>
        <ul>
          <li className="legend-row" data-kind="fire">
            <Icon name="marcador-anomalia" size={18} /> Anomalía: incendio
          </li>
          <li className="legend-row" data-kind="deforestation">
            <Icon name="marcador-anomalia" size={18} /> Anomalía: deforestación
          </li>
          <li className="legend-row" data-kind="report">
            <Icon name="marcador-reporte" size={18} /> Reporte ciudadano
          </li>
          <li className="legend-row" data-kind="hotspot">
            <Icon name="foco" size={18} /> Focos de calor (densidad)
          </li>
          <li className="legend-row" data-kind="zone">
            <Icon name="geocerca" size={18} /> Zona monitoreada
          </li>
        </ul>
      </div>
    </details>
  );
}
