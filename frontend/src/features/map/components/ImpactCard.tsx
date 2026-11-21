import { CountUp } from "@/shared/ui/CountUp";
import { formatNumber } from "../labels";

interface Props {
  title: string;
  hectares: number;
  co2Tonnes: number | null;
}

/** Impacto en cifras de instrumento, con conteo animado al aparecer o cambiar. */
export function ImpactCard({ title, hectares, co2Tonnes }: Props) {
  return (
    <section aria-label={title}>
      <h3>{title}</h3>
      <dl className="impact">
        <div className="impact-row">
          <dt className="visually-hidden">Superficie afectada</dt>
          <dd>
            <span className="impact-figure">
              <CountUp value={hectares} format={formatNumber} />
            </span>
            <span className="muted"> hectáreas</span>
          </dd>
        </div>
        <div className="impact-row">
          <dt className="visually-hidden">Carbono liberado, estimación</dt>
          <dd>
            <span className="impact-figure">
              {co2Tonnes === null ? "sin dato" : <CountUp value={co2Tonnes} format={formatNumber} />}
            </span>
            <span className="muted"> t de CO₂ (estimación)</span>
          </dd>
        </div>
      </dl>
    </section>
  );
}
