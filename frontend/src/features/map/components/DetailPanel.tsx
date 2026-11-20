"use client";

import {
  useAnomalyImages,
  useConfirmAnomaly,
  useZoneReadings,
} from "@/features/monitoring/api/queries";
import type { Role } from "@/shared/api/types";
import { ANOMALY_STATE_LABELS, ANOMALY_TYPE_LABELS, RISK_LABELS, formatDate, percent } from "../labels";
import type { DetailModel } from "../selection";
import { BeforeAfterSlider } from "./BeforeAfterSlider";
import { ImpactCard } from "./ImpactCard";
import { NdviChart } from "./NdviChart";

interface Props {
  detail: DetailModel;
  role: Role;
  onClose: () => void;
}

export function DetailPanel({ detail, role, onClose }: Props) {
  const images = useAnomalyImages(detail.anomalyId);
  const readings = useZoneReadings(detail.zoneId);
  const confirm = useConfirmAnomaly();

  const canConfirm =
    role === "ADMIN" && (detail.state === "DETECTADA" || detail.state === "EN_VERIFICACION");

  return (
    <aside className="panel detail-panel" aria-labelledby="detail-title">
      <header>
        <h2 id="detail-title">
          {detail.kind === "alert" ? "Alerta" : "Anomalía"} · {ANOMALY_TYPE_LABELS[detail.type]}
        </h2>
        <button type="button" onClick={onClose}>
          Cerrar detalle
        </button>
      </header>

      <section aria-label="Datos">
        <dl className="facts">
          <dt>Zona</dt>
          <dd>{detail.zoneName ?? "—"}</dd>
          {detail.state && (
            <>
              <dt>Estado</dt>
              <dd>{ANOMALY_STATE_LABELS[detail.state]}</dd>
            </>
          )}
          {detail.risk && (
            <>
              <dt>Riesgo</dt>
              <dd>
                <span className="risk" data-level={detail.risk}>
                  {RISK_LABELS[detail.risk]}
                </span>
              </dd>
            </>
          )}
          <dt>Confianza</dt>
          <dd>{percent(detail.confidence)}</dd>
          <dt>Detectada</dt>
          <dd>{formatDate(detail.detectedAt)}</dd>
          {detail.alertCreatedAt && (
            <>
              <dt>Alerta emitida</dt>
              <dd>{formatDate(detail.alertCreatedAt)}</dd>
            </>
          )}
        </dl>
        <ImpactCard title="Impacto" hectares={detail.hectares} co2Tonnes={detail.co2Tonnes} />
      </section>

      <section aria-label="Imágenes antes y después">
        <h3>Antes / después</h3>
        {images.isError ? (
          <div role="alert">
            <p className="error">No se pudieron cargar las imágenes.</p>
            <button type="button" onClick={() => images.refetch()}>
              Reintentar
            </button>
          </div>
        ) : (
          <BeforeAfterSlider
            beforeUrl={images.data?.before_url ?? null}
            afterUrl={images.data?.after_url ?? null}
            beforeDate={images.data?.before_date ?? detail.detectedAt}
            afterDate={images.data?.after_date ?? detail.detectedAt}
            loading={images.isFetching}
            onRetry={() => images.refetch()}
          />
        )}
      </section>

      <section aria-label="Serie NDVI de la zona">
        <h3>NDVI de la zona</h3>
        {readings.isPending && <p role="status">Cargando serie…</p>}
        {readings.isError && (
          <p role="alert" className="error">
            No se pudo cargar la serie.
          </p>
        )}
        {readings.data && <NdviChart data={readings.data} />}
      </section>

      {(canConfirm || confirm.isSuccess) && (
        <section aria-label="Acciones de administrador">
          {canConfirm && (
            <button
              type="button"
              className="primary"
              onClick={() => confirm.mutate(detail.anomalyId)}
              disabled={confirm.isPending}
              aria-busy={confirm.isPending}
            >
              {confirm.isPending ? "Confirmando…" : "Confirmar anomalía"}
            </button>
          )}
          {confirm.isSuccess && <p role="status">Anomalía confirmada. Se generó la alerta.</p>}
          {confirm.isError && (
            <p role="alert" className="error">
              {confirm.error.message}
            </p>
          )}
        </section>
      )}
    </aside>
  );
}
