import { formatNumber } from "../labels";

interface Props {
  title: string;
  hectares: number;
  co2Tonnes: number | null;
}

export function ImpactCard({ title, hectares, co2Tonnes }: Props) {
  return (
    <section className="impact-card" aria-label={title}>
      <h3>{title}</h3>
      <p>
        <span className="impact-figure">{formatNumber(hectares)} ha</span> afectadas
      </p>
      <p>
        <span className="impact-figure">
          {co2Tonnes === null ? "sin dato" : `${formatNumber(co2Tonnes)} t CO₂`}
        </span>{" "}
        <span className="muted">(estimación)</span>
      </p>
    </section>
  );
}
