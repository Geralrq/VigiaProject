import { formatNumber } from "../labels";

interface Props {
  title: string;
  hectares: number;
  co2Tonnes: number | null;
}

/** Impacto en cifras de instrumento. Sin caja: la jerarquía la da la tipografía. */
export function ImpactCard({ title, hectares, co2Tonnes }: Props) {
  return (
    <section aria-label={title}>
      <h3>{title}</h3>
      <dl className="impact">
        <div className="impact-row">
          <dt className="visually-hidden">Superficie afectada</dt>
          <dd>
            <span className="impact-figure">{formatNumber(hectares)}</span>
            <span className="muted"> hectáreas</span>
          </dd>
        </div>
        <div className="impact-row">
          <dt className="visually-hidden">Carbono liberado, estimación</dt>
          <dd>
            <span className="impact-figure">
              {co2Tonnes === null ? "sin dato" : formatNumber(co2Tonnes)}
            </span>
            <span className="muted"> t de CO₂ (estimación)</span>
          </dd>
        </div>
      </dl>
    </section>
  );
}
