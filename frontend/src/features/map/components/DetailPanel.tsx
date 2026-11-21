"use client";

import { useState } from "react";
import {
  useAnomalyImages,
  useConfirmAnomaly,
  useZoneReadings,
} from "@/features/monitoring/api/queries";
import type { Role } from "@/shared/api/types";
import { ConfirmDialog } from "@/shared/ui/ConfirmDialog";
import {
  ANOMALY_STATE_LABELS,
  ANOMALY_TYPE_LABELS,
  anomalyIcon,
  formatDate,
  percent,
} from "../labels";
import type { DetailModel } from "../selection";
import { BeforeAfterSlider } from "./BeforeAfterSlider";
import { ImpactCard } from "./ImpactCard";
import { NdviChart } from "./NdviChart";
import { RiskBadge } from "./RiskBadge";
import { UiIcon } from "@/shared/ui/icons/ui";
import { Icon } from "@/shared/ui/icons/Icon";
import { ErrorState, Skeleton } from "@/shared/ui/states";

interface Props {
  detail: DetailModel;
  role: Role;
  onClose: () => void;
}

export function DetailPanel({ detail, role, onClose }: Props) {
  const images = useAnomalyImages(detail.anomalyId);
  const readings = useZoneReadings(detail.zoneId);
  const confirm = useConfirmAnomaly();
  const [confirming, setConfirming] = useState(false);

  const canConfirm =
    role === "ADMIN" && (detail.state === "DETECTADA" || detail.state === "EN_VERIFICACION");

  return (
    <aside
      className="panel detail-panel"
      aria-labelledby="detail-title"
      data-risk={detail.risk ?? undefined}
    >
      <header>
        <h2 id="detail-title" className="title-with-icon">
          <Icon name={anomalyIcon(detail.type)} size={24} />
          {detail.kind === "alert" ? "Alerta" : "Anomalía"} de {ANOMALY_TYPE_LABELS[detail.type].toLowerCase()}
        </h2>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Cerrar detalle">
          <UiIcon name="cerrar" />
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
                <RiskBadge level={detail.risk} />
              </dd>
            </>
          )}
          <dt>Confianza</dt>
          <dd className="mono">{percent(detail.confidence)}</dd>
          <dt>Detectada</dt>
          <dd>
            <time dateTime={detail.detectedAt}>{formatDate(detail.detectedAt)}</time>
          </dd>
          {detail.alertCreatedAt && (
            <>
              <dt>Alerta emitida</dt>
              <dd>
                <time dateTime={detail.alertCreatedAt}>{formatDate(detail.alertCreatedAt)}</time>
              </dd>
            </>
          )}
        </dl>
        <ImpactCard title="Impacto" hectares={detail.hectares} co2Tonnes={detail.co2Tonnes} />
      </section>

      <section aria-label="Imágenes antes y después">
        <h3>Antes / después</h3>
        {images.isError ? (
          <ErrorState
            message="No se pudieron cargar las imágenes satelitales."
            onRetry={() => images.refetch()}
          />
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
        {readings.isPending && <Skeleton label="Cargando la serie NDVI…" variant="block" />}
        {readings.isError && (
          <ErrorState message="No se pudo cargar la serie NDVI." onRetry={() => readings.refetch()} />
        )}
        {readings.data && <NdviChart data={readings.data} />}
      </section>

      {(canConfirm || confirm.isSuccess) && (
        <section aria-label="Acciones de administrador">
          {canConfirm && (
            <button
              type="button"
              className="primary"
              onClick={() => setConfirming(true)}
              disabled={confirm.isPending}
              aria-haspopup="dialog"
            >
              Confirmar anomalía
            </button>
          )}
          <ConfirmDialog
            open={confirming}
            title="¿Confirmar esta anomalía?"
            confirmLabel={confirm.isPending ? "Confirmando…" : "Confirmar y alertar"}
            busy={confirm.isPending}
            onCancel={() => setConfirming(false)}
            onConfirm={() =>
              confirm.mutate(detail.anomalyId, { onSettled: () => setConfirming(false) })
            }
          >
            <p>
              Se generará una alerta y se notificará a las personas que están dentro de la zona de
              riesgo y a las autoridades.
            </p>
            <p>Confirma solo si ya verificaste que la anomalía es real. No se puede deshacer.</p>
          </ConfirmDialog>
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
