import type { ZoneReadings } from "@/shared/api/types";
import { formatDate, formatDecimal, formatNumber } from "../labels";

const WIDTH = 320;
const HEIGHT = 170;
const PAD = { top: 12, right: 12, bottom: 28, left: 36 };

/** Serie temporal del índice de la zona, en SVG propio, con la línea del umbral. */
export function NdviChart({ data }: { data: ZoneReadings }) {
  const points = data.readings.map((r) => ({ t: new Date(r.date).getTime(), v: r.value }));

  if (points.length === 0) {
    return <p className="muted">Sin lecturas de {data.index} en este período.</p>;
  }

  const values = [...points.map((p) => p.v), ...(data.threshold_line === null ? [] : [data.threshold_line])];
  const yMin = Math.floor((Math.min(...values) - 0.05) * 10) / 10;
  const yMax = Math.ceil((Math.max(...values) + 0.05) * 10) / 10;
  const tMin = points[0].t;
  const tMax = points[points.length - 1].t;

  const x = (t: number) =>
    PAD.left + (tMax === tMin ? 0.5 : (t - tMin) / (tMax - tMin)) * (WIDTH - PAD.left - PAD.right);
  const y = (v: number) =>
    PAD.top + (1 - (v - yMin) / (yMax - yMin)) * (HEIGHT - PAD.top - PAD.bottom);

  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ");
  const ticks = [yMin, (yMin + yMax) / 2, yMax];
  const last = data.readings[data.readings.length - 1];
  const summary =
    `Serie de ${data.index}: ${data.readings.length} lecturas, última ${formatNumber(last.value)} ` +
    `el ${formatDate(last.date)}` +
    (data.threshold_line === null ? "." : `; umbral ${formatNumber(data.threshold_line)}.`);

  return (
    <figure>
      <svg
        className="chart"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={summary}
      >
        {ticks.map((tick) => (
          <g key={tick}>
            <line className="chart-grid" x1={PAD.left} x2={WIDTH - PAD.right} y1={y(tick)} y2={y(tick)} />
            <text x={PAD.left - 4} y={y(tick)} textAnchor="end" dominantBaseline="middle">
              {formatDecimal(tick)}
            </text>
          </g>
        ))}
        <path className="chart-line" d={path} />
        {points.map((p) => (
          <circle key={p.t} className="chart-point" cx={x(p.t)} cy={y(p.v)} r={2.5} />
        ))}
        {data.threshold_line !== null && (
          <g>
            <line
              className="chart-threshold"
              x1={PAD.left}
              x2={WIDTH - PAD.right}
              y1={y(data.threshold_line)}
              y2={y(data.threshold_line)}
            />
            <text
              className="chart-threshold-label"
              x={WIDTH - PAD.right}
              y={y(data.threshold_line) - 4}
              textAnchor="end"
            >
              Umbral
            </text>
          </g>
        )}
        <text x={PAD.left} y={HEIGHT - 8}>
          {formatDate(data.readings[0].date)}
        </text>
        <text x={WIDTH - PAD.right} y={HEIGHT - 8} textAnchor="end">
          {formatDate(last.date)}
        </text>
      </svg>
      <figcaption className="muted">
        {data.index} de la zona, últimos {Math.round((tMax - tMin) / 86_400_000)} días. La línea
        punteada marca el umbral de alerta.
      </figcaption>
    </figure>
  );
}
