import Link from "next/link";
import { RiskBadge } from "@/features/map/components/RiskBadge";
import { ANOMALY_TYPE_LABELS, formatDate, formatNumber } from "@/features/map/labels";
import type { AnomalyType, PublicAlert } from "@/shared/api/types";

/** Ficha pública de una alerta. Componente de servidor: solo datos reducidos, sin ubicación. */
export function PublicAlertSheet({ alert }: { alert: PublicAlert }) {
  const typeLabel = ANOMALY_TYPE_LABELS[alert.type as AnomalyType] ?? alert.type;
  return (
    <main className="auth-page public-sheet">
      <p className="wordmark">Vigía</p>
      <h1>Alerta de {typeLabel.toLowerCase()}</h1>
      <p className="lede">
        Zona {alert.zone_name}. Ficha pública con datos resumidos de una alerta ambiental.
      </p>
      <dl className="facts">
        <dt>Riesgo</dt>
        <dd>
          <RiskBadge level={alert.risk_level} />
        </dd>
        <dt>Fecha</dt>
        <dd>
          <time dateTime={alert.date}>{formatDate(alert.date)}</time>
        </dd>
        <dt>Superficie</dt>
        <dd>{formatNumber(alert.hectares)}&nbsp;hectáreas</dd>
        <dt>Carbono</dt>
        <dd>
          {alert.co2_tonnes === null ? "sin dato" : `${formatNumber(alert.co2_tonnes)} t de CO₂`}{" "}
          <span className="muted">(estimación)</span>
        </dd>
      </dl>
      <p>
        <Link href="/login">Iniciar sesión para ver el detalle</Link>
      </p>
    </main>
  );
}
